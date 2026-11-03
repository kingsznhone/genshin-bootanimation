# WebUI 源码

模块卡片里的配置页。React 19 + TypeScript + MUI + Vite。

## 预览

```bash
cd webui
npm install       # 首次
npm run dev       # 打开终端里给出的地址（默认 http://localhost:5173/）
```

VS Code 里可以 `Ctrl+Shift+P` → **Simple Browser: Show** 打开该地址，改代码自动刷新。
浏览器里没有 `ksu` 桥接对象，读配置会回落到"默认"，点保存会提示 `ksu is not defined`，属正常。

## 构建

```bash
cd webui
npm install
npm run build     # 产物输出到 ../webroot，由 src/build.py 打进模块
```

`vite.config.ts` 里写死了 `outDir: '../webroot'` 和 `base: './'`——后者不能改，管理器是用
WebView 从本地加载页面，绝对路径会 404。

## 约定

- 产物目录 `webroot/` 要提交进仓库，打包脚本只读它，不跑 npm；
- 模块 id 用 `__ID__` 占位，`build.py` 打包时替换成真实 id（当前为 `genshin_bootanim`）；
- 执行命令用官方桥接库：

```ts
import { exec, toast } from 'kernelsu';
const { errno, stdout } = await exec('cat /data/adb/genshin_bootanim/config.conf');
```

- 配置文件是 `/data/adb/genshin_bootanim/config.conf`，内容形如 `SILENT=0`（key=value，
  shell 侧用 `grep -q '^SILENT=1$'` 读取，所以不要改成 JSON）。
- 开机时由 `post-fs-data.sh` 读取该配置：`SILENT=1` 删掉
  `/data/system/theme/boots/bootaudio.mp3`，否则从 `files/bootaudio.mp3` 复制过去。
