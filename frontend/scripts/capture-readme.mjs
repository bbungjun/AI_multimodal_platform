// Documentation capture only. Uses real app routes and the existing isolated QA fixture.
import { chromium } from "playwright";
import react from "@vitejs/plugin-react";
import { createServer } from "vite";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const output = resolve(root, "../output/playwright/readme");
let vite, browser, externalRequests = 0;
let phase = "startup";
const snapshots = [];
const sensitive = new Set();
const check = (condition) => { if (!condition) throw new Error("capture_check_failed"); };
const redact = value => {
  let text = value;
  for (const item of [...sensitive].sort((a, b) => b.length - a.length)) {
    if (item) text = text.split(item).join("[REDACTED]");
  }
  return text.replace(/[0-9a-f]{8}-[0-9a-f-]{27,}/gi, "[ID]")
    .replace(/https?:\/\/[^\s"<>]+/g, "[URL]")
    .replace(/[\w.+-]+@[\w.-]+/g, "[ACCOUNT]");
};
const capture = async (page, name, selector, masks = [], maxHeight = null) => {
  const region = page.locator(selector);
  await region.waitFor({ state: "visible" });
  await page.evaluate(() => document.fonts.ready);
  await page.evaluate(() => window.scrollTo(0, 0));
  const box = await region.boundingBox();
  check(box && box.width > 300 && box.height > 100);
  // Persist only heading/control snapshots, never arbitrary response-backed text.
  const controls = region.locator("h1, h2, h3, button, th, [role=progressbar]");
  const aria = [];
  for (const control of await controls.all()) aria.push(redact(await control.ariaSnapshot()));
  snapshots.push({ name, selector, viewport: { width: 1440, height: 900 },
    max_height: maxHeight, masked_selectors: masks, aria: aria.join("\n") });
  const options = { path: resolve(output, `${name}.png`), animations: "disabled",
    mask: masks.map(selector => page.locator(selector)), maskColor: "#334155" };
  if (maxHeight) {
    await page.screenshot({ ...options, fullPage: true,
      clip: { x: box.x, y: box.y, width: box.width, height: Math.min(box.height, maxHeight) } });
  } else await region.screenshot(options);
};

try {
  let raw = "";
  for await (const chunk of process.stdin) { raw += chunk; check(raw.length < 8192); }
  const start = JSON.parse(raw);
  check(start.frontend_origin === "http://127.0.0.1:18155"
    && /^http:\/\/127\.0\.0\.1:[0-9]+$/.test(start.backend_url)
    && Object.keys(start.secrets).sort().join(",") === "a,master"
    && Object.values(start.secrets).every(value => /^[A-Za-z0-9_-]{43}$/.test(value)));
  Object.values(start.secrets).forEach(value => sensitive.add(value));
  await mkdir(output, { recursive: true });
  vite = await createServer({ root, configFile: false, envFile: false, logLevel: "silent",
    plugins: [react()], define: { "import.meta.env.VITE_API_BASE": JSON.stringify("") },
    server: { host: "127.0.0.1", port: 18155, strictPort: true,
      proxy: { "/api": { target: start.backend_url }, "/files": { target: start.backend_url } } } });
  await vite.listen();
  browser = await chromium.launch({ headless: true });
  const pageFor = async secret => {
    const context = await browser.newContext({ baseURL: start.frontend_origin,
      viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1, serviceWorkers: "block" });
    await context.route("**/*", route => {
      if (new URL(route.request().url()).origin === start.frontend_origin) return route.continue();
      externalRequests += 1;
      return route.abort("blockedbyclient");
    });
    await context.addCookies([{ name: "creativeops_session", value: secret,
      url: start.frontend_origin, httpOnly: true, sameSite: "Lax", secure: false }]);
    const page = await context.newPage();
    page.setDefaultTimeout(15000);
    return page;
  };
  const page = await pageFor(start.secrets.a);
  phase = "studio";
  await page.goto("/generate");
  await page.locator(".creative-prompt-field textarea").first().fill("");
  await page.getByRole("heading", { name: "제목 없는 장면" }).waitFor();
  const health = await page.request.get(`${start.frontend_origin}/api/health`);
  check(health.ok() && (await health.json()).vertex.status === "mock_provider");
  await capture(page, "studio", ".creative-main", [".creative-account"]);

  phase = "prompt_review";
  const prompt = "A small ceramic studio beside a quiet forest";
  sensitive.add(prompt);
  await page.locator(".creative-prompt-field textarea").first().fill(prompt);
  await page.getByRole("button", { name: "향상", exact: true }).click();
  await page.getByRole("heading", { name: "향상된 프롬프트 검토" }).waitFor();
  for (const text of await page.locator(".prompt-box, .component-chip strong").allTextContents()) sensitive.add(text.trim());
  sensitive.add(await page.getByRole("textbox", { name: "편집 가능한 향상 프롬프트 초안" }).inputValue());
  await capture(page, "prompt-review", ".creative-enhance-drawer",
    [".prompt-box", ".creative-enhance-drawer textarea", ".component-list"]);
  await page.getByRole("button", { name: "초안 수락", exact: true }).click();
  await page.getByText("프롬프트 향상을 수락했습니다.", { exact: false }).waitFor();
  phase = "generation";
  const submitted = page.waitForResponse(response => response.url().endsWith("/api/generations")
    && response.request().method() === "POST");
  await page.locator('button[type="submit"]').click();
  const response = await submitted;
  check(response.status() === 201);
  const job = await response.json();
  sensitive.add(job.id); sensitive.add(job.id.slice(0, 8));
  await page.getByRole("heading", { name: /이미지 결과.*준비됨/ }).waitFor({ timeout: 30000 });
  await page.locator("img.asset-media").evaluate(image => image.decode());
  await capture(page, "generation-result", ".creative-detail-grid", [".prompt-detail"], 1035);

  phase = "usage";
  await page.goto("/usage");
  await page.getByRole("heading", { name: "플랜 및 사용량" }).waitFor();
  const usage = await page.request.get(`${start.frontend_origin}/api/usage/me`);
  const data = await usage.json();
  check(usage.ok() && Number(data.cycle.charged_microcredits) > 0 && data.credit.held_microcredits === 0);
  await capture(page, "usage", ".creative-page--usage");

  phase = "master";
  const master = await pageFor(start.secrets.master);
  await master.goto("/master");
  await master.getByRole("heading", { name: "크레딧 흐름", exact: true }).waitFor();
  await capture(master, "master", ".master-page", [".master-identity"], 1030);
  check(externalRequests === 0);
  await writeFile(resolve(output, "snapshots.json"), JSON.stringify({
    environment: "isolated mock; test-only sessions; real API/database/worker; no Google OAuth",
    snapshots,
  }, null, 2) + "\n");
  process.stdout.write(JSON.stringify({ complete: true, screenshots: 5, external_requests: 0,
    mock_generations: 1, prompt_reviews: 1 }));
} catch {
  process.stdout.write(JSON.stringify({ complete: false, phase }));
  process.exitCode = 1;
} finally {
  await browser?.close();
  await vite?.close();
}
