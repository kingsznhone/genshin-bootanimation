# AGENTS.md

给在这个仓库里干活的 agent 看的规则。都是踩过坑之后定下来的，别绕开。

## 这个仓库做什么

把 `assets/frames/`（1440x3200 母版帧，画面在画布里是横置的）按目标分辨率打成
KernelSU / Magisk 模块。唯一脚本 `src/build.py`，产物 `build/genshin-bootamin.zip`。

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

6. **模块 zip 用 deflate 9，绝对不要用 LZMA。**
   LZMA 能再小 2%（8.13 MiB），但 ksud 解不开，实测报 `unzip: corrupted data / inflate error`，
   装机直接失败。deflate 9 是验证过能装的（8.32 MiB，比 stored 小 10%）。
   内层 `bootanimation.zip` 的帧必须继续保持 STORED，那是 Android 的硬性要求。

## 构建

```bash
uv run python src/build.py 1080x2400              # 默认 30fps
uv run python src/build.py 2656x1220 --fps 24     # 降帧率
uv run python src/build.py 1080x2400 --silent     # 不带音频
```

素材是 1440x3200（9:20 竖构图），目标宽高比偏离越多裁得越多，这是预期行为，不要"修正"。

发布用的母版包：`uv run python src/build.py 1440x3200 -o build/genshin_bootanim-<code>-<version>.zip`

## 测试机

- Xiaomi 2211133C（fuxi），Android 16，`wm size` = 1080x2400
- KernelSU + Hybrid Mount（metamodule），overlay 模式下偶尔有 `overlayfs: failed to get metacopy (-13)`，
  这条在当前能正常显示的启动里也会出现，**不是**模块失败的证据
- `/system/media` → `/product/media` 软链

## 协作约定

- 不要每改一次就提交一个 commit，攒成一批再提交
- 需要重启时只发 `adb reboot` 就结束对话，不要 `wait-for-device`、不要 sleep 轮询、不要顺手查状态
- 判断"有没有生效"看 `/system/media/bootanimation.zip` 的大小，而不是靠猜
