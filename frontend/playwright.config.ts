import { defineConfig } from "@playwright/test";

// Prevent automatic DOM/error-context attachments containing fixture content.
process.env.PLAYWRIGHT_NO_COPY_PROMPT = "1";
const browserRun = process.argv.some((arg) => arg.includes("chromium"));
export default defineConfig({
  testDir: "./tests",
  outputDir: "../.omo/evidence/issue-101/runner",
  preserveOutput: "never",
  reporter: "dot",
  retries: 0,
  workers: 1,
  forbidOnly: !!process.env.CI,
  use: {
    baseURL: "http://127.0.0.1:18101",
    trace: "off", video: "off", screenshot: "off",
    serviceWorkers: "block",
  },
  projects: [
    { name: "session", testMatch: "auth-session.spec.ts" },
    { name: "chromium", testMatch: "auth-ux.spec.ts", use: { browserName: "chromium" } },
  ],
  webServer: browserRun ? {
    command: "npm run dev -- --host 127.0.0.1 --port 18101 --strictPort --mode auth-test",
    url: "http://127.0.0.1:18101",
    reuseExistingServer: false,
    env: { VITE_API_BASE: "", VITE_API_PROXY_TARGET: "http://127.0.0.1:1",
      AI_PROVIDER: "mock", GOOGLE_APPLICATION_CREDENTIALS: "",
      AUTH_GOOGLE_CLIENT_ID: "", AUTH_GOOGLE_CLIENT_SECRET: "" },
  } : undefined,
});
