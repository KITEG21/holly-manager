import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // En Docker sobre Windows las carpetas montadas no emiten eventos de cambio: hay que sondear
    watch: process.env.WATCH_POLLING ? { usePolling: true, interval: 300 } : undefined,
    proxy: {
      "/api": process.env.VITE_API_PROXY ?? "http://localhost:8010",
    },
  },
});
