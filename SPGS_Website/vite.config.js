import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: '0.0.0.0',
    allowedHosts: ['negligee-deity-skyward.ngrok-free.dev'],
    proxy: {
      '/spots': {
        target: 'http://100.115.173.108:8000',
        changeOrigin: true,
        secure: false,
      },
      '/docs': {
        target: 'http://100.115.173.108:8000',
        changeOrigin: true,
        secure: false,
      }
    }
  }
})