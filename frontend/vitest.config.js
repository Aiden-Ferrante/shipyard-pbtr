// Deliberately not vite.config.js: that config pulls tailwind and (via the app
// entry) the fleet-ui sibling clone, neither of which a component test needs —
// and the sibling may be absent on the machine running the tests.
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    include: ['tests/**/*.test.jsx'],
  },
})
