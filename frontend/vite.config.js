import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  define: {
    /*
     * Stamped when the bundle is built, not when the page renders. A footer
     * that reads `new Date()` at render always says "today", which is not a
     * last-updated date -- it is a clock, and it would claim the site was
     * updated on whatever day someone happens to open it.
     */
    __BUILD_DATE__: JSON.stringify(
      new Date().toISOString().slice(0, 10),
    ),
  },
  server: {
    port: 5173,
    // The dashboard talks to FastAPI on :8000. Proxying keeps the browser
    // same-origin, so uploads and static waterfall PNGs need no CORS dance.
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/static': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
