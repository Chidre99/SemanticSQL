import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Proxy /api → http://localhost:8000 in dev so the frontend can stay
// origin-agnostic. SSE works through the proxy because it's a long-lived
// HTTP response; Vite's http-proxy handles streaming.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
