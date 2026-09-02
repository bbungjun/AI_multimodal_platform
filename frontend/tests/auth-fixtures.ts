import { test as base, expect, type BrowserContext, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";

export const user = { id: "10000000-0000-4000-8000-000000000001", role: "user",
  status: "active", email: "fixture@example.test", display_name: "Fixture User", picture: null };
export const origin = "http://127.0.0.1:18101";
export const viewports = [{ width: 1440, height: 900 }, { width: 920, height: 900 },
  { width: 390, height: 844 }, { width: 320, height: 720 }];

export async function installHttp(context: BrowserContext) {
  const counts = { me: 0, work: 0, start: 0, logout: 0, external: 0, unexpected: 0,
    meStatus: 200, profile: user as unknown, holdMe: null as Promise<void> | null,
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
    mask: [page.locator(".creative-user-card, .creative-account, .creative-stage__copy h2, textarea, input")] });
}
export const test = base.extend<{ http: Awaited<ReturnType<typeof installHttp>> }>({
  http: [async ({ context }, use) => { const counts = await installHttp(context); await use(counts);
    expect(counts.external).toBe(0); expect(counts.unexpected).toBe(0);
  }, { auto: true }],
});
export { expect };
