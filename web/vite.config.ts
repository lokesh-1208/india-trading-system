import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the page runs on :5173 and asks the Python server (:8765) for data.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://127.0.0.1:8765" } },
  build: { outDir: "dist", emptyOutDir: true, chunkSizeWarningLimit: 900 },
});
