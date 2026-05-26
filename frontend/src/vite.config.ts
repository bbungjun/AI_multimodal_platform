import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

const parseAllowedHosts = (value: string | undefined) =>
  value
    ?.split(",")
    .map((host) => host.trim())
    .filter(Boolean) ?? [];

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const proxyTarget =
    env.VITE_API_PROXY_TARGET?.trim() || "http://localhost:8000";
  const allowedHosts = parseAllowedHosts(env.VITE_ALLOWED_HOSTS);

  return {
    plugins: [react()],
    server: {
      host: "0.0.0.0",
      port: 5173,
      ...(allowedHosts.length > 0 ? { allowedHosts } : {}),
      proxy: {
        "/api": {
          target: proxyTarget,
          changeOrigin: true,
        },
        "/files": {
          target: proxyTarget,
          changeOrigin: true,
        },
      },
    },
  };
});
