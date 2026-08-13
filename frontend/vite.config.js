import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

// Vite 配置
// 端口 5173(与后端 CORS 白名单一致)
// alias @ → src
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    host: 'localhost',
    open: false,
  },
})
