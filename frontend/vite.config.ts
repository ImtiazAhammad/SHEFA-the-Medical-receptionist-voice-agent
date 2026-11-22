import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'

const world = fileURLToPath(new URL('../src/shefa/static/world', import.meta.url))

// Built files go straight into the Python package, where FastAPI serves them at /app.
export default defineConfig({
  plugins: [react()],
  // The SHEFA world tokens and fonts live beside the Python package, shared with the collector.
  resolve: { alias: { '@world': world } },
  base: '/app-assets/',
  build: { outDir: '../src/shefa/static/app', emptyOutDir: true, assetsDir: 'assets' },
  server: { fs: { allow: ['..'] }, proxy: { '/api': 'http://127.0.0.1:8000', '/ws': { target: 'ws://127.0.0.1:8000', ws: true } } },
})
