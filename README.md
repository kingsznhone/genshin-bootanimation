# 原神开机动画（KernelSU）

<img src="assets/startup.jpg" width="420" alt="预览">

把 1440x3200 母版按手机分辨率打包成开机动画模块。小米 13（1080x2400 / HyperOS 3）、
小米 17（1220x2656 / HyperOS 4）实测通过。

## 用法

```bash
uv sync
uv run src/build.py                       # 不传分辨率 = 母版 1440x3200，输出 build/genshin-bootamin.zip
uv run src/build.py 1080x2400              # 指定分辨率
uv run src/build.py 1440x3200 --fps 24    # 降帧率减小体积
```

装法：KernelSU → 模块 → 从本地安装 → 选 `build/genshin-bootamin.zip` → 重启。

只支持 KernelSU（实测环境：KernelSU + Hybrid Mount），**不支持 Magisk**：模块 zip 不带
`META-INF/` 安装脚本，开机脚本里的模块路径和挂载行为也只在 KernelSU 上验证过。

## 用 GitHub Actions 打包

Fork → Actions → `build` → Run workflow，填 `resolution`（`adb shell wm size` 里的 Physical size）、
`fps`。产物是 artifact 里的 **`genshin-bootamin.zip`**——artifact 本身是个压缩包，要先解压。

## 规则

| | |
| --- | --- |
| 分辨率 | 命令行传入，cover 缩放：一条边齐平、另一边居中裁掉，不留黑边 |
| 方向 | 跟随母版，不旋转 |
| 帧率 | 默认 30，可降到 1–30，总时长固定 6 秒 |
| 画面 | 8-bit 灰度 PNG，64 级量化；180 帧去重后 13 parts / 136 文件 |
| 音频 | 10 秒，尾部 2 秒淡出已烘进文件；静音在 WebUI 里开关 |

宽高比越接近母版的 9:20，裁得越少。

## 模块内容

```
module.prop                        id 固定，换分辨率重装是更新
customize.sh                       分辨率对不上时提示
post-fs-data.sh                    按配置设开机音属性、铺 MIUI 主题音源
uninstall.sh                       还原属性 + 删掉铺过去的音效
webroot/                           WebUI 产物（配置页）
system/media/bootanimation.zip     desc.txt + partN + audio.wav（AOSP 用）
files/bootaudio.mp3                MIUI 的开机音源
```

只写 `/system/media`，不要往模块里加 `product/`——会让整块模块挂不上。

开机音的位置随系统不同：

| 系统 | 音源 | 读取方式 |
| --- | --- | --- |
| AOSP | `part0/audio.wav`（在 zip 里） | `audioplay` |
| MIUI / HyperOS | `/data/system/theme/boots/bootaudio.mp3` | `playBackgroundMusic`，由脚本每次开机铺 |

静音统一由两个属性控制（`persist.sys.bootanim.play_sound`、`persist.sys.boot_audio.enabled`），
由 `post-fs-data.sh` 按 `/data/adb/genshin_bootanim/config.conf` 的 `SILENT` 设置，
卸载时还原。

## WebUI

`webui/` 是配置页源码（React + TypeScript + MUI + Vite），`webroot/` 是构建产物；
`src/build.py` 只负责把 `webroot/` 整个目录打进模块，不跑 npm。

``ash
cd webui && npm install && npm run build   # 产物直接输出到 webroot/
``
## 版本号

改 `pyproject.toml` 的 `version`，`versionCode` 自动推导（`1.0.1` → `10001`）。

## 已知问题

HyperOS 4 上如果手机里文件极多（百万级），开机时 SELinux 全盘重打标签会拖慢启动，
音频服务来不及就绪，表现为动画正常但没有声音。清理文件可以缓解。
