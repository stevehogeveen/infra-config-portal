import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const proxyTarget = process.env.APP_PROXY_TARGET ?? "http://127.0.0.1:8002";
const host = process.env.FRONTEND_HOST ?? "127.0.0.1";
const port = Number(process.env.FRONTEND_PORT ?? "5173");

export default defineConfig({
  plugins: [react()],
  server: {
    host,
    port,
    strictPort: true,
    proxy: {
      "/api": proxyTarget,
      "/health": proxyTarget
    }
  }
});
