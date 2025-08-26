import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // proxy API + static assets to FastAPI (dev only)
      '/api': 'http://localhost:8020',
      '/static': 'http://localhost:8020'
    }
  }
})
