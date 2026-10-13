import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The UI talks to the API under /api. In development Vite proxies that to the FastAPI process.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8000" } },
  build: { outDir: "dist", sourcemap: false },
});
