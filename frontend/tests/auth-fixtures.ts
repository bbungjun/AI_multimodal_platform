import { test as base, expect, type BrowserContext, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";

export const user = { id: "10000000-0000-4000-8000-000000000001", role: "user",
  status: "active", email: "fixture@example.test", display_name: "Fixture User", picture: null };
export const origin = "http://127.0.0.1:18101";
export const viewports = [{ width: 1440, height: 900 }, { width: 920, height: 900 },
  { width: 390, height: 844 }, { width: 320, height: 720 }];
export const usage = {
  plan: "pro", pending_plan: "free", rate_card_version: "v1",
  cycle: { index: 2, starts_at: "2026-08-20T03:00:00Z", renews_at: "2026-09-19T03:00:00Z",
    allowance_microcredits: 2_000_000_000, charged_microcredits: 510_250_000 },
  credit: { available_microcredits: 1_489_750_000, held_microcredits: 12_000_000 },
  concurrency: { active_requests: 2, limit: 3 },
  usage: [
    { meter: "gemini_input_token", unit: "token", observed_units: 12_500, charged_microcredits: 12_500_000 },
    { meter: "gemini_output_token", unit: "token", observed_units: 3_400, charged_microcredits: 17_000_000 },
    { meter: "imagen_fast_image", unit: "image", observed_units: 8, charged_microcredits: 80_000_000 },
    { meter: "imagen_standard_image", unit: "image", observed_units: 4, charged_microcredits: 120_000_000 },
    { meter: "imagen_ultra_image", unit: "image", observed_units: 1, charged_microcredits: 80_000_000 },
    { meter: "veo_fast_ms", unit: "millisecond", observed_units: 20_000, charged_microcredits: 100_000_000 },
    { meter: "veo_standard_ms", unit: "millisecond", observed_units: 10_000, charged_microcredits: 100_750_000 },
  ],
};

export async function installHttp(context: BrowserContext) {
  const counts = { me: 0, work: 0, usage: 0, start: 0, logout: 0, external: 0, unexpected: 0,
    meStatus: 200, profile: user as unknown, holdMe: null as Promise<void> | null,
    usageStatus: 200, usageBody: usage as unknown, holdUsage: null as Promise<void> | null,
    logoutStatus: 204, holdLogout: null as Promise<void> | null, startError: "" };
  await context.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== origin) { counts.external++; await route.abort(); return; }
    if (url.pathname === "/api/auth/me") { counts.me++; await counts.holdMe;
      await route.fulfill({ status: counts.meStatus, json: counts.profile }); return; }
    if (url.pathname === "/api/auth/google/start") {
      counts.start++;
      const location = counts.startError ? `/login?auth_error=${counts.startError}` : url.searchParams.get("return_to") || "/generate";
      if (!counts.startError) counts.meStatus = 200;
      await route.fulfill({ status: 303, headers: { location } }); return;
    }
    if (url.pathname === "/api/auth/logout") {
      counts.logout++; await counts.holdLogout;
      if (counts.logoutStatus === 204) counts.meStatus = 401;
      await route.fulfill({ status: counts.logoutStatus }); return;
    }
    if (url.pathname === "/api/health") { await route.fulfill({ json: { ok: true, db: "up" } }); return; }
    if (url.pathname === "/api/usage/me") { counts.usage++; await counts.holdUsage;
      await route.fulfill({ status: counts.usageStatus, json: counts.usageBody }); return; }
    if (url.pathname === "/api/generations" && route.request().method() === "GET") {
      counts.work++; await route.fulfill({ json: [] }); return;
    }
    if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/files/")) {
      counts.unexpected++; await route.abort(); return;
    }
    await route.continue();
  });
  return counts;
}
export async function maskedScreenshot(page: Page, name: string) {
  await mkdir("../.omo/evidence/issue-101/screens", { recursive: true });
  await page.screenshot({ path: `../.omo/evidence/issue-101/screens/${name}.png`, fullPage: true,
    mask: [page.locator(".creative-user-card, .creative-account, .creative-account-details strong, .creative-account-details p, .creative-stage__copy, textarea, input")] });
}
export const test = base.extend<{ http: Awaited<ReturnType<typeof installHttp>> }>({
  http: [async ({ context }, use) => { const counts = await installHttp(context); await use(counts);
    expect(counts.external).toBe(0); expect(counts.unexpected).toBe(0);
  }, { auto: true }],
});
export { expect };
