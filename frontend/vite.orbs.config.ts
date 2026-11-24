import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The standalone orbs module for the non-React pages (see src/orbs/standalone.tsx). It has its
// own output folder in the shared world, so the main app build (which empties static/app) never
// touches it, and this build only ever empties world/orbs.
export default defineConfig({
  plugins: [react()],
  define: { 'process.env.NODE_ENV': JSON.stringify('production') },
  build: {
    outDir: '../src/shefa/static/world/orbs',
    emptyOutDir: true,
    minify: true, // a library build leaves ES output unminified by default (Vite 8: oxc)
    lib: { entry: 'src/orbs/standalone.tsx', formats: ['es'], fileName: () => 'shefa-orbs.js' },
    rollupOptions: { output: { inlineDynamicImports: true, minify: true } },
  },
})
