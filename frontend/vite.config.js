import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The API port is a variable so the browser tests can point the proxy at their own
// backend instead of the one you have running for development.
const API_PORT = process.env.VITE_API_PORT || '8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': `http://127.0.0.1:${API_PORT}`,
    },
  },
})
