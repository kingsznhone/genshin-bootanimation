# AGENTS.md

给在这个仓库里干活的 agent 看的规则。都是踩过坑之后定下来的，别绕开。

## 这个仓库做什么

把 `assets/frames/`（1440x3200 母版帧，画面在画布里是横置的）按目标分辨率打成
KernelSU 模块。唯一脚本 `src/build.py`，产物 `build/genshin-bootamin.zip`。
模块里的 shell 脚本（customize / post-fs-data / uninstall）在 `src/ksu-scripts/`，
`__ID__` / `__SIZE__` / `__MD5__` 占位符由 `build.py` 打包时替换。

## 硬性规则

1. **绝对禁止旋转母版。**
   素材是什么方向就出什么方向，构建只做 cover 缩放 + 居中裁切。
   不要加 `--rotate`、不要 `transpose`、不要"顺手帮用户转正"。
   用户明确要求过三次。目标分辨率给横屏（比如 2656x1220）就按横屏出。

2. **模块里只写 `system/media/`，不要生成 `product/`。**
   测试机的 `/system/media` 是 `/product/media` 的软链，KSU 会自动把模块的
   `system/media` 映射到 `/product/media`；模块里再放一份 `product/` 会导致
   整个模块挂载失败，表现是开机动画完全消失（不是黑屏，是回默认动画）。

3. **帧用 8-bit 灰度 PNG（color type 0）+ 64 级量化。**
   这是验证过能正常播放的配置。调色板（color type 3）、256 级、L 模式各种组合都试过，
   没有额外收益，只会引入变量。

4. **装完必须重启才生效。**
   `ksud module list` 里 `update: true`、`/data/adb/modules_update/<id>` 存在，
   都说明新模块还在等下一次开机。没重启就判断"没效果"等于白测。

5. **一次只改一个变量。**
   之前同时改了布局、颜色类型、量化级数，结果三次失败无法归因，浪费了一轮。

6. **开机音：属性当总开关，文件只当音源。**
   `post-fs-data.sh` 每次开机按 `/data/adb/genshin_bootanim/config.conf` 的 `SILENT` 设置：
   `SILENT=1` → `persist.sys.bootanim.play_sound=0`、`persist.sys.boot_audio.enabled=0`；
   否则两个都设成 `1`，并把 `files/bootaudio.mp3` 复制到 `/data/system/theme/boots/bootaudio.mp3`。
   `uninstall.sh` 必须把两个属性还原成 `1`，否则模块卸载后手机永远没开机音。
   **不要**把 mp3 放进 `system/media/`：`/system/media` 是 `/product/media` 的软链，
   那份会成为 MIUI 的回落路径，绕开属性开关（实测）。
   内层 `bootanimation.zip` 要保留 `part0/audio.wav` 供 AOSP 的 audioplay；静音已经由属性负责，
   不需要为了静音把它删掉。

7. **模块 zip 用 deflate 9，绝对不要用 LZMA。**
   LZMA 能再小 2%（8.13 MiB），但 ksud 解不开，实测报 `unzip: corrupted data / inflate error`，
   装机直接失败。deflate 9 是验证过能装的（8.32 MiB，比 stored 小 10%）。
   内层 `bootanimation.zip` 的帧必须继续保持 STORED，那是 Android 的硬性要求。

8. **只支持 KernelSU，不支持 Magisk。**
   不要加 `META-INF/com/google/android/update-binary` / `updater-script`，不要为 Magisk 改脚本路径
   或挂载方式，文档里也不要写"KernelSU / Magisk"。所有行为只在 KSU 上验证过。

9. **构建不带静音参数。**
   音效永远打进包里，静音是运行时开关（`config.conf` 的 `SILENT`）。
   不要再加 `--silent` 之类的构建选项。

## 构建

```bash
uv run src/build.py                        # 不传分辨率 = 母版 1440x3200，默认 30fps
uv run src/build.py 1080x2400
uv run src/build.py 2656x1220 --fps 24     # 降帧率
```

WebUI 源码在 `webui/`（React + TS + MUI + Vite），产物在 `webui/dist/`（不入库）：

```bash
cd webui && npm ci && npm run build     # 输出到 webui/dist/
```

`build.py` 把 `webui/dist/` 整个目录打进模块的 `webroot/`，不跑 npm；CI 里先构建 WebUI 再跑 `build.py`。

素材是 1440x3200（9:20 竖构图），目标宽高比偏离越多裁得越多，这是预期行为，不要"修正"。

发布用的母版包：`uv run src/build.py 1440x3200 -o build/genshin_bootanim-<code>-<version>.zip`

## 实测事实（别再重新踩）

- `/system/media` 是软链，指向 `/product/media`；原厂动画的物理文件是
  `/product/media/bootanimation.zip`，`/system/media/bootanimation.zip` 只是同一个文件。
- KSU 的 `post-fs-data.sh` 里 **`$MODPATH` 是空的**，脚本里要用绝对路径
  `/data/adb/modules/<id>/`，或者 `${MODPATH:-/data/adb/modules/<id>}` 兜底。
- 模块**不带** `system/media/bootanimation.zip` 时，可以在 `post-fs-data.sh` 里
  `mount -o bind` 到 `/system/media/bootanimation.zip`（会落到 `/product/media/...`），
  bootanimation 能读到，实测有效。
- 模块**带了**静态 `system/media/bootanimation.zip` 时，KSU 会在模块挂载阶段（脚本之后）
  再挂一次，压住脚本 bind 的那层——想动态替换就不要带静态文件。
- MIUI 的 `playBackgroundMusic` 有回落：主题目录没有文件时会播 `/product/media/bootaudio.mp3`，
  所以模块里不能再放这份 mp3。
- `persist.sys.bootanim.play_sound` / `persist.sys.boot_audio.enabled` 是开机音总开关，
  实测两个都设 0 后，即使主题目录里有 mp3 也不响；ksu 域 setprop 可写（rc=0），值持久化。
- bind 只对本次开机有效。

## 测试机

- Xiaomi 2211133C（fuxi），Android 16，`wm size` = 1080x2400
- Xiaomi 25113PN0EC（pudding），Android 17 / OS4.0，`wm size` = 1220x2656
- KernelSU + Hybrid Mount（metamodule），overlay 模式下偶尔有 `overlayfs: failed to get metacopy (-13)`，
  这条在当前能正常显示的启动里也会出现，**不是**模块失败的证据

## 协作约定

- 不要每改一次就提交一个 commit，攒成一批再提交
- 需要重启时只发 `adb reboot` 就结束对话，不要 `wait-for-device`、不要 sleep 轮询、不要顺手查状态
- 判断"有没有生效"看 `/system/media/bootanimation.zip` 的大小，而不是靠猜
