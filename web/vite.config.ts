import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Dev: `npm run dev` proxies /api to the live server (or VITE_API_TARGET, e.g. http://127.0.0.1:8000).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { proxy: { "/api": { target: process.env.VITE_API_TARGET ?? "https://pam.is-cool.dev", changeOrigin: true } } },
  build: { sourcemap: false, chunkSizeWarningLimit: 700 },
  test: { environment: "node" },
});
