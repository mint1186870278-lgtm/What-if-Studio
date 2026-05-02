import { defineConfig } from "vite";

export default defineConfig({
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:3567",
        changeOrigin: true
      }
    }
  }
});
