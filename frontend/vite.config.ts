import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    proxy: {
      // Backend faellt auf 5000 zurueck wenn Port 80 nicht gebunden werden
      // kann (Windows-Dev ohne Admin) — siehe preflight() in gallery_server.py.
      "/api":      { target: "http://127.0.0.1:5000", changeOrigin: true },
      "/img":      { target: "http://127.0.0.1:5000", changeOrigin: true },
      "/thumb":    { target: "http://127.0.0.1:5000", changeOrigin: true },
      "/preview":  { target: "http://127.0.0.1:5000", changeOrigin: true },
      "/download": { target: "http://127.0.0.1:5000", changeOrigin: true },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});
