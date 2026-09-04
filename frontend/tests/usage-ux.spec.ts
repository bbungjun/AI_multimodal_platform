import { test, expect, maskedScreenshot, usage, user, viewports } from "./auth-fixtures";

test("personal usage renders the G9A snapshot without model inference", async ({ page, http }) => {
  await page.goto("/usage");
  await expect(page.getByRole("heading", { name: "플랜 및 사용량" })).toBeVisible();
  await expect(page.getByText("Pro", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Free로 변경 예정")).toBeVisible();
  await expect(page.getByText("1,489.75")).toBeVisible();
  await expect(page.getByRole("row", { name: /Gemini 입력/ })).toContainText("12,500 토큰");
  await expect(page.getByRole("row", { name: /Veo Standard/ })).toContainText("10,000 ms");
  await expect(page.getByText(/정확한 모델별 청구서가 아닙니다/)).toBeVisible();
  expect(http.usage).toBe(1);
});

test("loading does not mount private values", async ({ page, http }) => {
  let release!: () => void;
  http.holdUsage = new Promise((resolve) => { release = resolve; });
  await page.goto("/usage");
  await expect(page.getByRole("status")).toContainText("사용량을 불러오는 중");
  await expect(page.getByText("1,489.75")).toHaveCount(0);
  release();
  await expect(page.getByText("1,489.75")).toBeVisible();
});

for (const scenario of ["busy", "unavailable", "network", "invalid"] as const) {
  test(`bounded failure and retry ${scenario}`, async ({ page, context, http }) => {
    if (scenario === "network") await context.route("**/api/usage/me", (route) => route.abort());
    else if (scenario === "invalid") http.usageBody = { ...usage, plan: "enterprise" };
    else { http.usageStatus = 503; http.usageBody = { detail: `usage_${scenario}` }; }
    await page.goto("/usage");
    const alert = page.getByRole("alert");
    await expect(alert).toBeVisible();
    await expect(alert).not.toContainText("enterprise");
    await expect(alert).not.toContainText("usage_");
    if (scenario !== "network") {
      http.usageStatus = 200; http.usageBody = usage;
      await page.getByRole("button", { name: "다시 시도" }).click();
      await expect(page.getByText("1,489.75")).toBeVisible();
      expect(http.usage).toBe(2);
    }
  });
}

test("manual refresh is single flight and preserves current snapshot", async ({ page, http }) => {
  await page.goto("/usage");
  await expect(page.getByText("1,489.75")).toBeVisible();
  let release!: () => void;
  http.holdUsage = new Promise((resolve) => { release = resolve; });
  const refresh = page.getByRole("button", { name: "사용량 새로고침" });
  await refresh.click();
  await expect(refresh).toBeDisabled();
  await expect(page.getByText("1,489.75")).toBeVisible();
  expect(http.usage).toBe(2);
  release();
  await expect(refresh).toBeEnabled();
});

test("usage 401 hands control to the Session gate", async ({ page, http }) => {
  http.usageStatus = 401;
  http.usageBody = { detail: "authentication_required" };
  await page.goto("/usage");
  await expect(page.getByRole("button", { name: "Google로 계속하기" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "플랜 및 사용량" })).toHaveCount(0);
});

test("late old-account usage cannot render after Session epoch change", async ({ page, context, http }) => {
  let release!: () => void;
  const pending = new Promise<void>((resolve) => { release = resolve; });
  let calls = 0;
  await context.route("**/api/usage/me", async (route) => {
    calls++;
    if (calls === 1) await pending;
    await route.fulfill({ json: usage });
  });
  await page.goto("/usage");
  await expect.poll(() => calls).toBe(1);
  http.profile = { ...user, id: "10000000-0000-4000-8000-000000000002" };
  await page.evaluate(() => { const c = new BroadcastChannel("creativeops.session"); c.postMessage("session-changed"); c.close(); });
  await expect.poll(() => calls).toBe(2);
  release();
  await expect(page.getByText("1,489.75")).toBeVisible();
  expect(calls).toBe(2);
});

for (const viewport of viewports) {
  test(`responsive usage workspace ${viewport.width}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto("/usage");
    await expect(page.getByRole("heading", { name: "플랜 및 사용량" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    const progress = page.getByRole("progressbar");
    await expect(progress).toHaveCount(3);
    await expect(page.getByRole("button", { name: "사용량 새로고침" })).toBeVisible();
    await maskedScreenshot(page, `usage-${viewport.width}`, "issue-134");
  });
}
