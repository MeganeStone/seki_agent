import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',  // 允许外部访问
    port: 5173,
    strictPort: false, // 端口冲突时自动尝试下一个
    hmr: {
      host: '192.168.144.22', // 替换为实际局域网 IP（如 192.168.x.x）
      protocol: 'ws'      // 强制使用 WebSocket 协议
    }
  }
})
