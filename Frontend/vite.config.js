import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Proxy /api calls to FastAPI so the browser sees one origin (no CORS fuss in dev).
export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    strictPort: true,
    allowedHosts: [".devtunnels.ms"],
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
