import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: process.env.PLEIADES_DEV_API_TARGET || 'http://127.0.0.1:5000', changeOrigin: true },
    },
  },
})
