import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// 产物直接进 webroot/，由 src/build.py 打进模块。
// base 必须是相对路径：管理器用 WebView 从本地加载，没有服务器。
export default defineConfig({
  base: './',
  plugins: [react()],
  build: {
    outDir: '../webroot',
    emptyOutDir: true,
    target: 'es2020',
    assetsDir: 'assets',
  },
});
