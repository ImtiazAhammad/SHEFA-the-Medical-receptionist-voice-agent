import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Built files go straight into the Python package, where FastAPI serves them at /app.
export default defineConfig({
  plugins: [react()],
  base: '/app-assets/',
  build: { outDir: '../src/shefa/static/app', emptyOutDir: true, assetsDir: 'assets' },
  server: { proxy: { '/api': 'http://127.0.0.1:8000', '/ws': { target: 'ws://127.0.0.1:8000', ws: true } } },
})
