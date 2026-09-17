import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// Vite config for the Phase 15 React frontend.
// The app is a static, read-only presentation layer: it fetches the real
// backend data artifact `dashboard_data.json` from `public/` (same-origin).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    open: false,
  },
  build: {
    outDir: 'dist',
  },
});
