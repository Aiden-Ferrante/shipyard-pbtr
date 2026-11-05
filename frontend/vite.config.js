import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// The dev server proxies to the API port (SHIPYARD_PORT, default 8845).
const API = `http://localhost:${process.env.SHIPYARD_PORT || 8845}`

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': API,
      '/health': API,
    },
  },
})
