import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Forward every request that starts with /api to Django.
    // The browser only talks to one server, so there are no CORS issues.
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})