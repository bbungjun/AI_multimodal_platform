import { chromium } from "@playwright/test";
import { createServer } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { createInterface } from "node:readline";

export const GROUPS = ["login_start", "callback_session", "profile", "logout", "replay_refusal", "relogin"];
const LOOPBACK = /^http:\/\/127\.0\.0\.1:[0-9]+$/;

export function validateStart(value) {
  if (!value || Object.keys(value).sort().join(",") !== "backend_url,frontend_origin,type" || value.type !== "start" ||
      !LOOPBACK.test(value.backend_url) || value.frontend_origin !== "http://127.0.0.1:18156") throw new Error("start_invalid");
  return value;
}

function emit(value) {
  process.stdout.write(`${JSON.stringify(value)}\n`);
}

async function readStart() {
  const lines = createInterface({ input: process.stdin, crlfDelay: Infinity });
  for await (const line of lines) {
    if (!line || line.length > 1024) throw new Error("start_invalid");
    return validateStart(JSON.parse(line));
  }
  throw new Error("start_invalid");
}

function check(value, code) {
  if (!value) throw new Error(code);
}

async function main() {
  let browser;
  let vite;
  let externalRequests = 0;
  let checks = 0;
  let phase = "startup";
  const ok = (value, code) => { check(value, code); checks++; };
  try {
    const start = await readStart();
    const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
    vite = await createServer({
      root, configFile: false, envFile: false, logLevel: "silent", plugins: [react()],
      server: { host: "127.0.0.1", port: 18156, strictPort: true,
        proxy: { "/api": { target: start.backend_url }, "/files": { target: start.backend_url } } },
      define: { "import.meta.env.VITE_API_BASE": JSON.stringify("") },
    });
    await vite.listen();
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ baseURL: start.frontend_origin, serviceWorkers: "block" });
    await context.route("**/*", async (route) => {
      const url = new URL(route.request().url());
      if (url.origin !== start.frontend_origin) {
        externalRequests++;
        await route.abort();
        return;
      }
      await route.continue();
    });
    const page = await context.newPage();
    let callbackPath = "";
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (url.pathname === "/api/auth/google/callback") callbackPath = url.pathname + url.search;
    });

    phase = "login_start";
    await page.goto("/login");
    const login = page.getByRole("button", { name: "Google로 계속하기" });
    await login.waitFor();
    await login.click();
    await page.waitForURL(/\/generate$/);
    ok(callbackPath.startsWith("/api/auth/google/callback?"), "callback_missing");

    phase = "callback_session";
    await page.locator(".creative-generate").waitFor();
    ok(await page.locator(".creative-generate").isVisible(), "workspace_missing");
    ok(externalRequests === 0, "external_request_seen");

    phase = "profile";
    const profile = await page.evaluate(async () => {
      const response = await fetch("/api/auth/me", { credentials: "same-origin", cache: "no-store" });
      const body = response.ok ? await response.json() : null;
      return { status: response.status, role: body?.role, state: body?.status };
    });
    ok(profile.status === 200 && profile.role === "user" && profile.state === "active", "profile_invalid");

    phase = "logout";
    await page.getByRole("button", { name: "계정 정보", exact: true }).click();
    await page.getByRole("button", { name: "로그아웃", exact: true }).click();
    await page.waitForURL(/\/login$/);
    ok(await login.isVisible(), "logout_gate_missing");
    const afterLogout = await page.evaluate(async () => (await fetch("/api/auth/me", {
      credentials: "same-origin", cache: "no-store",
    })).status);
    ok(afterLogout === 401, "logout_session_active");

    phase = "replay_refusal";
    await page.goto(callbackPath);
    await page.waitForURL(/\/login$/);
    ok(await page.getByRole("alert").getByText("로그인을 완료하지 못했습니다", { exact: false }).isVisible(),
      "replay_error_missing");
    ok((await page.evaluate(async () => (await fetch("/api/auth/me", { credentials: "same-origin" })).status)) === 401,
      "replay_created_session");

    phase = "relogin";
    await page.getByRole("button", { name: "Google로 계속하기" }).click();
    await page.waitForURL(/\/generate$/);
    await page.locator(".creative-generate").waitFor();
    ok(await page.locator(".creative-generate").isVisible(), "relogin_workspace_missing");
    ok(externalRequests === 0, "external_request_seen");

    await context.close();
    emit({ type: "complete", groups: GROUPS.length, checks, external_requests: externalRequests });
  } catch {
    emit({ type: "failed", phase: GROUPS.includes(phase) ? phase : "startup", code: "mock_oauth_browser_failed" });
    process.exitCode = 1;
  } finally {
    if (browser) await browser.close().catch(() => {});
    if (vite) await vite.close().catch(() => {});
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) await main();
