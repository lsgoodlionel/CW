import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 开发时把 /api 反代到后端,避免跨域
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
