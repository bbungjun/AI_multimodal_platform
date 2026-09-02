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
