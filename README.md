# KernelSU原神开机动画模块

1440p 母版 → 目标分辨率的 KernelSU / Magisk 模块，

在小米13 小米17上测试通过

## 用法

```bash
uv sync
uv run python src/build.py 1440x3200     # 母版原生，产物 build/genshin-bootamin.zip
uv run python src/build.py 1080x2400
uv run python src/build.py 1440x3200 --fps 24    # 降帧率换体积
uv run python src/build.py 1440x3200 --silent   # 不带音频
```

装法：KernelSU / Magisk → 模块 → 从本地安装 → 选 `build/genshin-bootamin.zip` → 重启。

## 定制化模块打包

fork 之后直接用 GitHub Actions：

1. **Fork** 本仓库
2. 进 **Actions → build → Run workflow**
3. 填三个参数：
   - `resolution`：手机的物理分辨率，`adb shell wm size` 里 `Physical size` 那一行的值（如 `1440x3200`）
   - `fps`：1–30，越小包越小（母版就是 30）
   - `silent`：勾上就不带开机音
4. 跑完在本次 run 页面底部下载 **Artifacts**：`genshin-bootamin-<分辨率>-<帧率>fps`
   （下载得到的本身是个 zip，**要先解压**，里面的 `genshin-bootamin.zip` 才是模块）
5. 在 KernelSU / Magisk 里装 `genshin-bootamin.zip`，而不是外层那个 artifact 压缩包

想改灰度级数、帧率上限这类默认值，改 `src/build.py` 顶部的常量再 push。

## 结构

```
assets/frames/    母版帧 1440x3200
assets/audio/     audio.wav（进 bootanimation.zip）/ bootaudio.mp3（MIUI·HyperOS）
src/build.py      唯一脚本：缩放 + 打包 + 自检
build/            产物模块（gitignore）
```

帧统一转 8-bit 灰度 PNG（color type 0），最高压缩（`compress_level=9`），180 帧按 CPU 核数并行。

模块内容：

```
module.prop                          模块信息（id 固定，换分辨率重装是更新而不是并存）
customize.sh                         设权限 + 分辨率不匹配时提示
system/media/bootanimation.zip       desc.txt + part0..partN + audio.wav
system/media/bootaudio.mp3           MIUI / HyperOS 开机音
```

只写 `/system/media` 一条路径。别在模块里生成 `product/` 目录：KSU 装了 Hybrid Mount 这类
metamodule 时，`/product` 的 overlay 可能挂不上（dmesg 里是 `overlayfs: failed to get metacopy`），
整块模块都不生效，表现是开机动画直接消失。`customize.sh` 只做权限和分辨率提示，不搬文件。

模块版本号取自 `pyproject.toml` 的 `[project].version`，`versionCode` 由它推出（`1.2.3` → `10203`），
发新版只要改 pyproject 里的版本。

## 规则

| 项 | 值 |
| --- | --- |
| 分辨率 | 命令行传入；cover 缩放，一条边齐平、另一边居中裁掉，不出黑边 |
| 方向 | 跟随母版，不旋转、不补边 |
| 帧率 | 默认母版的 30 fps，`--fps` 可降到 1–30；总时长固定 6 秒 |
| desc.txt | 按连续重复帧自动分段，`c COUNT 0 partN` |
| 音频 | 10 秒，尾部 2 秒线性淡出已烘进文件 |

`c` = 这段必须播完，开机结束也不打断；6 秒画面走完就退出。
180 帧里有 44 帧是连续重复的（最长 15 帧），构建时只存 1 张、用 `COUNT` 撑时长，
最终压成 13 个 part / 136 个文件。

音频两份都带：`part0/audio.wav`（AOSP 原生机制，16-bit PCM）和 `system/media/bootaudio.mp3`
（MIUI / HyperOS 系统级播放）。不想要声音加 `--silent`。

目标分辨率的宽高比最好接近母版的 9:20，差得越多裁得越多。
