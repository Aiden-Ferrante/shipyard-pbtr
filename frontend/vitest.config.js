// Deliberately not vite.config.js: that config pulls tailwind, which a component
// test does not need.
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    include: ['tests/**/*.test.jsx'],
  },
})
