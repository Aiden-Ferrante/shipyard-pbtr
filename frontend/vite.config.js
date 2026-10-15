import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': 'http://localhost:8845',
      '/health': 'http://localhost:8845',
    },
    // styles.css and App.jsx import code/fleet-ui, which lives above this repo.
    // The prod build resolves it; the dev server refuses without being told, and
    // the failure is a blank unstyled page.
    fs: { allow: ['..', '../../fleet-ui'] },
  },
})
