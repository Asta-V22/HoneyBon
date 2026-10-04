import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // Same-origin API in dev so the httpOnly session cookie just works.
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
});
