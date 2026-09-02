import { test, expect, maskedScreenshot, viewports, user } from "./auth-fixtures";

for (const viewport of viewports) {
  test(`existing workspace layout ${viewport.width}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto("/generate");
    await expect(page.locator(".creative-generate")).toBeVisible();
    await maskedScreenshot(page, `authenticated-${viewport.width}`);
  });
}

test("checking never mounts private history and StrictMode coalesces me", async ({ page, http }) => {
  let release!: () => void; http.holdMe = new Promise((r) => { release = r; });
  await page.goto("/history");
  await expect(page.getByRole("heading", { name: "로그인 상태 확인 중" })).toBeVisible();
  expect(http.me).toBe(1); expect(http.work).toBe(0);
  release(); await expect.poll(() => http.work).toBe(1);
});
test("anonymous deep link starts native login once and verifies callback", async ({ page, http }) => {
  http.meStatus = 401; await page.goto("/history");
  await expect(page.getByRole("button", { name: "Google로 계속하기" })).toBeVisible();
  expect(http.work).toBe(0);
  await page.getByRole("button", { name: "Google로 계속하기" }).click();
  await expect(page).toHaveURL(/\/history$/);
  await expect.poll(() => http.me).toBe(2); expect(http.start).toBe(1);
  await expect.poll(() => http.work).toBe(1);
});
for (const scenario of ["503", "malformed", "network", "timeout"]) test(`bootstrap unavailable ${scenario}`, async ({ page, context, http }) => {
  if (scenario === "503") http.meStatus = 503;
  if (scenario === "malformed") http.profile = { ...user, role: "invalid" };
  if (scenario === "network") await context.route("**/api/auth/me", (route) => route.abort());
  if (scenario === "timeout") {
    await page.clock.install();
    await context.route("**/api/auth/me", () => new Promise(() => {}));
  }
  await page.goto("/history");
  if (scenario === "timeout") await page.clock.runFor(10_001);
  await expect(page.getByRole("heading", { name: "로그인 상태를 확인할 수 없습니다." })).toBeVisible();
  expect(http.work).toBe(0);
});
for (const path of ["/?auth_error=oauth_denied", "/login?auth_error=unknown&code=discard&state=discard"]) test(`safe callback error ${path.startsWith('/?') ? 'root' : 'login'}`, async ({ page, http }) => {
  http.meStatus = 401; await page.goto(path);
  await expect(page.getByRole("alert")).toContainText("로그인을 완료하지 못했습니다");
  await expect(page).toHaveURL(/\/login$/);
  await page.reload(); await expect(page.getByRole("button", { name: "Google로 계속하기" })).toBeVisible();
  expect(http.work).toBe(0);
});
test("start failure stays inside safe login UI", async ({ page, http }) => {
  http.meStatus = 401; http.startError = "auth_not_configured"; await page.goto("/login");
  await page.getByRole("button", { name: "Google로 계속하기" }).click();
  await expect(page.getByRole("alert")).toContainText("로그인을 완료하지 못했습니다");
  await expect(page).toHaveURL(/\/login$/); expect(http.start).toBe(1);
});
test("authenticated login route redirects to workspace", async ({ page }) => {
  await page.goto("/login"); await expect(page.locator(".creative-generate")).toBeVisible();
  await expect(page).toHaveURL(/\/generate$/);
});

for (const status of [204, 403, 503]) test(`logout outcome ${status}`, async ({ page, http }) => {
  http.logoutStatus = status; await page.goto("/generate");
  await page.getByRole("button", { name: "계정 정보", exact: true }).click();
  let release!: () => void; http.holdLogout = new Promise((r) => { release = r; });
  await page.getByRole("button", { name: "로그아웃", exact: true }).click();
  await expect(page.locator(".creative-generate")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "로그아웃 확인 중" })).toBeVisible();
  expect(http.logout).toBe(1); release();
  if (status === 204) await expect(page.getByRole("status")).toContainText("로그아웃되었습니다");
  else {
    await expect(page.getByRole("heading", { name: "로그아웃 완료를 확인할 수 없습니다." })).toBeVisible();
    await expect(page.getByText("로그아웃되었습니다.", { exact: true })).toHaveCount(0);
    await page.getByRole("button", { name: "다시 확인", exact: true }).click();
    await expect(page.locator(".creative-generate")).toBeVisible();
  }
});
test("idle has no auth heartbeat and healthy activity retains form", async ({ page, http }) => {
  await page.clock.install(); await page.goto("/generate");
  const textarea = page.locator("textarea").first(); await textarea.fill("UNSAVED_TEST_INPUT");
  await page.clock.fastForward(12 * 60 * 60 * 1000);
  expect(http.me).toBe(1);
  await textarea.press("ArrowLeft"); await expect.poll(() => http.me).toBe(2);
  await expect(textarea).toHaveValue("UNSAVED_TEST_INPUT");
  http.meStatus = 401; await page.clock.fastForward(300_000); await textarea.press("ArrowRight");
  await expect(page.getByRole("status")).toContainText("로그인이 만료되었거나 종료");
  await expect(page.locator("textarea")).toHaveCount(0);
});
test("sibling logout locks and rechecks without broadcast loop", async ({ page, context, http }) => {
  await page.goto("/generate"); await expect(page.locator(".creative-generate")).toBeVisible();
  const sibling = await context.newPage(); await sibling.goto("/generate");
  await expect(sibling.locator(".creative-generate")).toBeVisible(); expect(http.me).toBe(2);
  await page.getByRole("button", { name: "계정 정보", exact: true }).click();
  await page.getByRole("button", { name: "로그아웃", exact: true }).click();
  await expect(sibling.getByRole("button", { name: "Google로 계속하기" })).toBeVisible();
  expect(http.me).toBe(3); await sibling.close();
});
test("BroadcastChannel unsupported uses focus revalidation", async ({ page, http }) => {
  await page.addInitScript(() => { Object.defineProperty(window, "BroadcastChannel", { value: undefined }); });
  await page.clock.install(); await page.goto("/generate"); await expect(page.locator(".creative-generate")).toBeVisible();
  http.meStatus = 401; await page.clock.fastForward(300_000);
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.getByRole("button", { name: "Google로 계속하기" })).toBeVisible(); expect(http.me).toBe(2);
});
for (const status of [200, 401]) test(`old account history response ${status} cannot affect new account`, async ({ page, context, http }) => {
  let release!: () => void; const pending = new Promise<void>((r) => { release = r; }); let calls = 0;
  await context.route("**/api/generations*", async (route) => {
    calls++; if (calls === 1) { await pending; await route.fulfill({ status, json: [] }); }
    else await route.fulfill({ json: [] });
  });
  await page.goto("/history"); await expect.poll(() => calls).toBe(1);
  http.profile = { ...user, id: "10000000-0000-4000-8000-000000000002", display_name: "Second Fixture" };
  await page.evaluate(() => { const channel = new BroadcastChannel("creativeops.session"); channel.postMessage("session-changed"); channel.close(); });
  await expect.poll(() => calls).toBe(2);
  const finished = page.waitForResponse((r) => r.url().includes("/api/generations") && r.status() === status);
  release(); await finished;
  await expect(page.getByRole("button", { name: "계정 정보", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Google로 계속하기" })).toHaveCount(0);
});
test("old mutation success cannot navigate the next account", async ({ page, context, http }) => {
  let release!: () => void; const pending = new Promise<void>((r) => { release = r; }); let posts = 0;
  await context.route("**/api/generations", async (route) => {
    if (route.request().method() !== "POST") { await route.fallback(); return; }
    posts++; await pending; await route.fulfill({ json: { id: user.id, assets: [] } });
  });
  await page.goto("/generate"); await page.getByRole("button", { name: "생성", exact: true }).click();
  await expect.poll(() => posts).toBe(1);
  http.profile = { ...user, id: "10000000-0000-4000-8000-000000000002" };
  await page.evaluate(() => { const c = new BroadcastChannel("creativeops.session"); c.postMessage("session-changed"); c.close(); });
  await expect.poll(() => http.me).toBe(2); await expect(page.getByRole("button", { name: "생성", exact: true })).toBeEnabled();
  const response = page.waitForResponse((r) => r.url().includes("/api/generations")); release(); await response;
  await expect(page).toHaveURL(/\/generate$/); expect(posts).toBe(1);
});

for (const failure of ["network", "timeout"]) test(`logout unconfirmed ${failure}`, async ({ page, context }) => {
  if (failure === "timeout") await page.clock.install();
  await context.route("**/api/auth/logout", failure === "network" ? (route) => route.abort() : () => new Promise(() => {}));
  await page.goto("/generate"); await page.getByRole("button", { name: "계정 정보", exact: true }).click();
  await page.getByRole("button", { name: "로그아웃", exact: true }).click();
  if (failure === "timeout") await page.clock.runFor(10_001);
  await expect(page.getByRole("heading", { name: "로그아웃 완료를 확인할 수 없습니다." })).toBeVisible();
  await expect(page.locator(".creative-generate")).toHaveCount(0);
});
test("hidden activity does not validate; stale me after logout cannot restore UI", async ({ page, http }) => {
  await page.clock.install(); await page.goto("/generate");
  await expect(page.locator(".creative-generate")).toBeVisible();
  await page.clock.fastForward(300_000);
  await page.evaluate(() => Object.defineProperty(document, "visibilityState", { configurable: true, get: () => "hidden" }));
  await page.keyboard.press("ArrowLeft"); expect(http.me).toBe(1);
  await page.evaluate(() => Object.defineProperty(document, "visibilityState", { configurable: true, get: () => "visible" }));
  let release!: () => void; http.holdMe = new Promise((r) => { release = r; });
  await page.getByRole("button", { name: "계정 정보", exact: true }).click();
  await expect.poll(() => http.me).toBe(2);
  await page.getByRole("button", { name: "로그아웃", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("로그아웃되었습니다");
  http.meStatus = 200; release();
  await expect(page.locator(".creative-generate")).toHaveCount(0);
});
