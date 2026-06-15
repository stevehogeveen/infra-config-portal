import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const proxyTarget = process.env.APP_PROXY_TARGET ?? "http://127.0.0.1:8001";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": proxyTarget,
      "/health": proxyTarget
    }
  }
});
