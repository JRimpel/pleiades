import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Flask runs on 5001 locally (see backend/.flaskenv) because macOS AirPlay
// occupies port 5000. Override with API_PROXY_TARGET=http://host:port npm run dev.
const apiTarget = process.env.API_PROXY_TARGET ?? 'http://localhost:5001'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
<<<<<<< HEAD
      '/api': { target: process.env.PLEIADES_DEV_API_TARGET || 'http://127.0.0.1:5000', changeOrigin: true },
=======
      '/api': apiTarget,
>>>>>>> 316d78010979697cd916b8318a9824a734ab9056
    },
  },
})
