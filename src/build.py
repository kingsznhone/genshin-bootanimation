#!/usr/bin/env python3
"""把 assets/ 里的母版按目标分辨率打成 KernelSU / Magisk 模块。

    uv run python src/build.py 1440x3200
    uv run python src/build.py 1080x2400 -o build/1080p.zip
    uv run python src/build.py 1440x3200 --silent

母版: assets/frames/IMG000.png ...
音频: assets/audio/audio.wav、bootaudio.mp3（--silent 时不带）
产物: build/genshin-bootamin.zip
"""

from __future__ import annotations

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
AUDIO_WAV = ROOT / "assets" / "audio" / "audio.wav"
AUDIO_MP3 = ROOT / "assets" / "audio" / "bootaudio.mp3"
OUT = ROOT / "build"

MASTER_FPS = 30  # 母版帧率
MODULE_ID = "genshin_bootanim"
MODULE_AUTHOR = "ZNH"
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

set_perm_recursive "$MODPATH/system/media" 0 0 0755 0644

if command -v wm >/dev/null 2>&1; then
    REAL="$(wm size 2>/dev/null | tail -n 1 | sed 's/.*: *//')"
    if [ -n "$REAL" ] && [ "$REAL" != "__SIZE__" ]; then
        ui_print "! 当前设备 $REAL，与本模块 __SIZE__ 不一致，画面会被裁切或留边"
    fi
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


def _write(zf: zipfile.ZipFile, name: str, data: bytes, compress: int = zipfile.ZIP_STORED) -> None:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = compress
    info.external_attr = 0o644 << 16
    zf.writestr(info, data)


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


def write_bootanimation(width, height, parts, zip_path, silent, fps):
    desc = [f"{width} {height} {fps}"]
    desc += [f"c {count} 0 part{i}" for i, (_, count) in enumerate(parts)]

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:
        _write(zf, "desc.txt", ("\n".join(desc) + "\n").encode())
        for i, (frames, _) in enumerate(parts):
            for j, frame in enumerate(frames):
                _write(zf, f"part{i}/f{j:04d}.png", frame.read_bytes())
        if not silent and AUDIO_WAV.exists():
            _write(zf, "part0/audio.wav", AUDIO_WAV.read_bytes())


def write_module(width, height, inner, out_path, silent, fps):
    size = f"{width}x{height}"
    tags = f"[{fps}FPS]" + ("[静音]" if silent else "")
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
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", compression=method, compresslevel=9) as zf:
        _write(zf, "module.prop", module_prop.encode(), method)
        _write(zf, "customize.sh", CUSTOMIZE.replace("__SIZE__", size).encode(), method)
        _write(zf, "system/media/bootanimation.zip", inner.read_bytes(), method)
        if not silent and AUDIO_MP3.exists():
            _write(zf, "system/media/bootaudio.mp3", AUDIO_MP3.read_bytes(), method)


# --------------------------------------------------------------------------- #


def resample(frames: list[Path], fps: int) -> list[Path]:
    """把 30fps 的母版按目标帧率重采样（就近取帧，时长不变）。"""
    if fps == MASTER_FPS:
        return frames
    count = max(1, round(len(frames) * fps / MASTER_FPS))
    return [frames[min(len(frames) - 1, round(i * MASTER_FPS / fps))] for i in range(count)]


def build(width: int, height: int, out_path: Path, keep_frames: bool, silent: bool, fps: int) -> Path:
    frames = resample(sorted(FRAMES.glob("IMG*.png")), fps)
    if not frames:
        raise BuildError(f"找不到母版帧：{FRAMES}")

    work = OUT / ".work"
    rendered = render_frames(frames, width, height, work / "frames")
    parts = group_frames(rendered)
    if sum(len(f) * c for f, c in parts) != len(rendered):
        raise BuildError("重复帧分组后的总帧数与母版不一致")

    inner = work / "bootanimation.zip"
    write_bootanimation(width, height, parts, inner, silent, fps)
    write_module(width, height, inner, out_path, silent, fps)

    if not keep_frames:
        shutil.rmtree(work, ignore_errors=True)

    files = sum(len(f) for f, _ in parts)
    print(f"{width}x{height} @{fps}fps  {len(rendered)} 帧 -> {len(parts)} parts / {files} 文件  "
          f"{out_path.stat().st_size / 1024 / 1024:.1f} MiB  -> {out_path}")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="build.py", description="按目标分辨率打包 KSU/Magisk 模块")
    parser.add_argument("size", help="目标分辨率，如 1440x3200")
    parser.add_argument("-o", "--out", help="输出模块路径，默认 build/genshin-bootamin.zip")
    parser.add_argument("--fps", type=int, default=MASTER_FPS, help=f"输出帧率 1–{MASTER_FPS}，默认 {MASTER_FPS}")
    parser.add_argument("--keep-frames", action="store_true", help="保留 build/.work 里的中间帧")
    parser.add_argument("--silent", action="store_true", help="不带音频")
    args = parser.parse_args(argv)

    try:
        if not 1 <= args.fps <= MASTER_FPS:
            raise BuildError(f"帧率只能是 1–{MASTER_FPS}（母版就是 {MASTER_FPS}fps，不做上采样）")
        out = Path(args.out) if args.out else Path("build") / "genshin-bootamin.zip"
        build(*parse_size(args.size), Path.cwd() / out, args.keep_frames, args.silent, args.fps)
    except BuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
