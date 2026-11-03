#!/usr/bin/env python3
"""把 assets/ 里的母版按目标分辨率打成 KernelSU 模块（不支持 Magisk）。

    uv run python src/build.py                     # 不传分辨率就是母版 1440x3200
    uv run python src/build.py 1080x2400 -o build/1080p.zip
    uv run python src/build.py --fps 24

母版: assets/frames/IMG000.png ...
音频: assets/audio/bootaudio.mp3（静音由 WebUI 开关控制，构建时总是带上）
产物: build/genshin-bootamin.zip
"""

import argparse
import hashlib
import os
import re
import shutil
import sys
import tomllib
import zipfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
FRAMES = ROOT / "assets" / "frames"
AUDIO_WAV = ROOT / "assets" / "audio" / "audio.wav"  # AOSP audioplay 从 zip 里读
AUDIO_MP3 = ROOT / "assets" / "audio" / "bootaudio.mp3"
OUT = ROOT / "build"

MASTER_FPS = 30  # 母版帧率
MASTER_SIZE = (1440, 3200)  # 母版分辨率，不传 size 时用它
MODULE_ID = "genshin_bootanim"
MODULE_AUTHOR = "ZNH"
WEBUI = ROOT / "webroot"  # 前端产物目录，由 webui/ 构建而来
PNG_LEVEL = 9  # zlib 最高压缩
GRAY_LEVELS = 64  # 灰度级数，越小帧越小
_GRAY_STEP = 256 // GRAY_LEVELS
GRAY_LUT = [min(255, v // _GRAY_STEP * _GRAY_STEP + _GRAY_STEP // 2) for v in range(256)]

# Windows 控制台默认不是 UTF-8，中文会乱码
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

_meta = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
VERSION = str(_meta["project"]["version"])
VERSION_CODE = max(
    1, sum(int(n) * 100 ** (2 - i) for i, n in enumerate(re.findall(r"\d+", VERSION)[:3]))
)

CUSTOMIZE = """#!/system/bin/sh
ui_print "- 原神开机动画"
ui_print "- 重启后生效"

if command -v wm >/dev/null 2>&1; then
    REAL="$(wm size 2>/dev/null | tail -n 1 | sed 's/.*: *//')"
    if [ -n "$REAL" ] && [ "$REAL" != "__SIZE__" ]; then
        ui_print "! 当前设备 $REAL，与本模块 __SIZE__ 不一致，画面会被裁切或留边"
    fi
fi
"""

# 开机音总开关：AOSP 的 audioplay 看 persist.sys.bootanim.play_sound，
# MIUI 的 playBackgroundMusic 看 persist.sys.boot_audio.enabled。
# 两者都是 persist 属性，卸载时要在 uninstall.sh 里还原。
# KSU 执行 post-fs-data.sh 时不设 $MODPATH，路径必须写死。
POST_FS_DATA = """#!/system/bin/sh
MODDIR=/data/adb/modules/__ID__
CONF=/data/adb/genshin_bootanim/config.conf
DST=/data/system/theme/boots/bootaudio.mp3
SRC="$MODDIR/files/bootaudio.mp3"

MUTE=0
if [ -f "$CONF" ] && grep -q '^SILENT=1$' "$CONF"; then
    MUTE=1
fi

if [ "$MUTE" = "1" ]; then
    setprop persist.sys.bootanim.play_sound 0
    setprop persist.sys.boot_audio.enabled 0
else
    setprop persist.sys.bootanim.play_sound 1
    setprop persist.sys.boot_audio.enabled 1
    if [ -f "$SRC" ]; then
        mkdir -p "${DST%/*}"
        cp -f "$SRC" "$DST"
        chmod 644 "$DST"
        chown 0:0 "$DST" 2>/dev/null
        restorecon "$DST" 2>/dev/null
    fi
fi
"""

UNINSTALL = """#!/system/bin/sh
# 模块没了就别继续压着系统开关
setprop persist.sys.bootanim.play_sound 1
setprop persist.sys.boot_audio.enabled 1

# 只删我们自己放过去的那份，别误删用户的主题铃声
DST=/data/system/theme/boots/bootaudio.mp3
if [ -f "$DST" ] && [ "$(md5sum "$DST" 2>/dev/null | cut -d' ' -f1)" = "__MD5__" ]; then
    rm -f "$DST"
fi
"""


class BuildError(RuntimeError):
    pass


def parse_size(text: str) -> tuple[int, int]:
    match = re.fullmatch(r"\s*(\d{2,5})\s*[xX*×]\s*(\d{2,5})\s*", text)
    if not match:
        raise BuildError(f"分辨率格式不对：{text!r}（示例：1920x1080）")
    width, height = int(match.group(1)), int(match.group(2))
    if min(width, height) < 16:
        raise BuildError(f"分辨率太小：{width}x{height}")
    return width, height


# --------------------------------------------------------------------------- #
# 缩放 + 压缩（一帧一个任务，交给进程池）


def _render_one(job: tuple[str, str, int, int]) -> None:
    src, dst, width, height = job
    with Image.open(src) as im:
        im = im.convert("L")  # 母版是灰度图
        if im.size != (width, height):
            im = ImageOps.fit(im, (width, height), method=Image.Resampling.LANCZOS)
        im = im.point(GRAY_LUT)  # 量化到 GRAY_LEVELS 级
    im.save(dst, format="PNG", compress_level=PNG_LEVEL, optimize=True)


def render_frames(frames: list[Path], width: int, height: int, dest: Path) -> list[Path]:
    """cover 缩放：等比放到刚好盖住目标，多余的部分居中裁掉。不旋转。"""
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)

    jobs = [(str(src), str(dest / f"f{i:04d}.png"), width, height) for i, src in enumerate(frames)]
    with ProcessPoolExecutor(max_workers=min(os.cpu_count() or 1, len(jobs))) as pool:
        list(pool.map(_render_one, jobs, chunksize=4))
    return sorted(dest.glob("f*.png"))


# --------------------------------------------------------------------------- #
# 打包


def _write(
    zf: zipfile.ZipFile, name: str, data: bytes, compress: int = zipfile.ZIP_STORED, mode: int = 0o644
) -> None:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = compress
    info.external_attr = (0o100000 | mode) << 16
    zf.writestr(info, data)


# 前端产物里可能有 __ID__ 占位符，这几类文件按文本处理
TEXT_SUFFIXES = {".html", ".js", ".mjs", ".css", ".json", ".svg", ".map", ".txt"}


def _write_webui(zf: zipfile.ZipFile, compress: int) -> None:
    """把 webroot/ 整个目录打进去（前端产物由使用者自己 build）。"""
    if not WEBUI.is_dir():
        raise BuildError(f"缺少前端产物目录：{WEBUI}（先构建 WebUI，或删掉 webroot 相关配置）")
    index = WEBUI / "index.html"
    if not index.is_file():
        raise BuildError(f"{index} 不存在，WebUI 入口缺失")

    for path in sorted(WEBUI.rglob("*")):
        if not path.is_file():
            continue
        arc = path.relative_to(ROOT).as_posix()  # webroot/...
        data = path.read_bytes()
        if path.suffix.lower() in TEXT_SUFFIXES:
            data = data.decode("utf-8").replace("__ID__", MODULE_ID).encode()
        _write(zf, arc, data, compress)


def group_frames(frames: list[Path]) -> list[tuple[list[Path], int]]:
    """把连续的相同帧压成 (帧列表, 重复次数)。count>1 的 part 只存 1 帧。"""
    hashes = [hashlib.md5(f.read_bytes()).digest() for f in frames]
    parts: list[tuple[list[Path], int]] = []
    batch: list[Path] = []
    i = 0
    while i < len(frames):
        j = i
        while j + 1 < len(frames) and hashes[j + 1] == hashes[i]:
            j += 1
        if j == i:  # 单帧，攒进当前多帧 part
            batch.append(frames[i])
        else:
            if batch:
                parts.append((batch, 1))
                batch = []
            parts.append(([frames[i]], j - i + 1))
        i = j + 1
    if batch:
        parts.append((batch, 1))
    return parts


def write_bootanimation(
    width: int, height: int, parts: list[tuple[list[Path], int]], zip_path: Path, fps: int
) -> None:
    desc = [f"{width} {height} {fps}"]
    desc += [f"c {count} 0 part{i}" for i, (_, count) in enumerate(parts)]

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:
        _write(zf, "desc.txt", ("\n".join(desc) + "\n").encode())
        for i, (frames, _) in enumerate(parts):
            for j, frame in enumerate(frames):
                _write(zf, f"part{i}/f{j:04d}.png", frame.read_bytes())
        # AOSP 的 audioplay 只吃 zip 里的 audio.wav；静音由 persist 属性控制
        if AUDIO_WAV.exists():
            _write(zf, "part0/audio.wav", AUDIO_WAV.read_bytes())


def write_module(width: int, height: int, inner: Path, out_path: Path, fps: int) -> None:
    size = f"{width}x{height}"
    tags = f"[{fps}FPS]"
    module_prop = (
        f"id={MODULE_ID}\n"
        f"name=原神开机动画 {tags}\n"
        f"version={VERSION}\n"
        f"versionCode={VERSION_CODE}\n"
        f"author={MODULE_AUTHOR}\n"
        f"description=将开机动画替换成原神启动动画，适配分辨率 {size}\n"
    )

    # deflate 9：比 stored 小约 10%。LZMA 还能再小 2%，但 ksud 解不开（unzip: inflate error）
    method = zipfile.ZIP_DEFLATED
    mp3 = AUDIO_MP3.read_bytes()
    md5 = hashlib.md5(mp3).hexdigest()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", compression=method, compresslevel=9) as zf:
        _write(zf, "module.prop", module_prop.encode(), method)
        _write(zf, "customize.sh", CUSTOMIZE.replace("__SIZE__", size).encode(), method, 0o755)
        _write(zf, "post-fs-data.sh", POST_FS_DATA.replace("__ID__", MODULE_ID).encode(), method, 0o755)
        uninstall = UNINSTALL.replace("__MD5__", md5)
        _write(zf, "uninstall.sh", uninstall.encode(), method, 0o755)
        _write_webui(zf, method)
        _write(zf, "system/media/bootanimation.zip", inner.read_bytes(), method)
        _write(zf, "files/bootaudio.mp3", mp3, method)


# --------------------------------------------------------------------------- #


def resample(frames: list[Path], fps: int) -> list[Path]:
    """把 30fps 的母版按目标帧率重采样（就近取帧，时长不变）。"""
    if fps == MASTER_FPS:
        return frames
    count = max(1, round(len(frames) * fps / MASTER_FPS))
    return [frames[min(len(frames) - 1, round(i * MASTER_FPS / fps))] for i in range(count)]


def build(width: int, height: int, out_path: Path, keep_frames: bool, fps: int) -> Path:
    frames = resample(sorted(FRAMES.glob("IMG*.png")), fps)
    if not frames:
        raise BuildError(f"找不到母版帧：{FRAMES}")

    work = OUT / ".work"
    rendered = render_frames(frames, width, height, work / "frames")
    parts = group_frames(rendered)
    if sum(len(f) * c for f, c in parts) != len(rendered):
        raise BuildError("重复帧分组后的总帧数与母版不一致")

    inner = work / "bootanimation.zip"
    write_bootanimation(width, height, parts, inner, fps)
    write_module(width, height, inner, out_path, fps)

    if not keep_frames:
        shutil.rmtree(work, ignore_errors=True)

    files = sum(len(f) for f, _ in parts)
    print(f"{width}x{height} @{fps}fps  {len(rendered)} 帧 -> {len(parts)} parts / {files} 文件  "
          f"{out_path.stat().st_size / 1024 / 1024:.1f} MiB  -> {out_path}")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="build.py", description="按目标分辨率打包 KernelSU 模块")
    parser.add_argument(
        "size", nargs="?", help=f"目标分辨率，默认母版 {MASTER_SIZE[0]}x{MASTER_SIZE[1]}"
    )
    parser.add_argument("-o", "--out", help="输出模块路径，默认 build/genshin-bootamin.zip")
    parser.add_argument("--fps", type=int, default=MASTER_FPS, help=f"输出帧率 1–{MASTER_FPS}，默认 {MASTER_FPS}")
    parser.add_argument("--keep-frames", action="store_true", help="保留 build/.work 里的中间帧")
    args = parser.parse_args(argv)

    try:
        if not 1 <= args.fps <= MASTER_FPS:
            raise BuildError(f"帧率只能是 1–{MASTER_FPS}（母版就是 {MASTER_FPS}fps，不做上采样）")
        width, height = parse_size(args.size) if args.size else MASTER_SIZE
        out = Path(args.out) if args.out else Path("build") / "genshin-bootamin.zip"
        build(width, height, Path.cwd() / out, args.keep_frames, args.fps)
    except BuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
