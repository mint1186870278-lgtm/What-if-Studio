import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  // Use one backend for HTTP/SSE and WebSocket requests. This setting stays
  // in the dev server, so browsers on other machines can use the same origin.
  const env = loadEnv(mode, import.meta.dirname, "DEV_");
  const backendTarget = env.DEV_API_TARGET || "http://127.0.0.1:8000";

  return {
    server: {
      host: "127.0.0.1",
      port: 5180,
      strictPort: true,
      proxy: {
        "/api": {
          target: backendTarget,
          changeOrigin: true,
        },
        "/ws": {
          target: backendTarget,
          ws: true,
        },
      },
    },
    build: {
      outDir: "dist",
      emptyOutDir: true,
    },
  };
});
