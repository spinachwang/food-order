import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
// Vitest 配置独立在 vitest.config.ts（vite.config.ts 的类型不允许带 test 块）
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    // F050 §4.1: 前端 fetch('/api/v1/...') 由 Vite dev server 代理到后端 :8000,
    // 避免 CORS 配置。生产构建由 nginx/反代承担同源责任。
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})