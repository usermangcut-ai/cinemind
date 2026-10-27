import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// host: true → nghe cả IPv4 lẫn IPv6 (mở được bằng localhost, 127.0.0.1, hoặc IP LAN)
export default defineConfig({
  plugins: [react()],
  server: { host: true, port: 5173 },
  preview: { host: true, port: 4173 },
})
