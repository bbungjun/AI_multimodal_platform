import { mkdir } from "node:fs/promises";
import { test, expect, user, member, target } from "./master-fixtures";

test("normal User cannot directly access console or discover menu", async ({ page, http, master }) => {
  http.profile = user;
  await page.goto("/master");
  await expect(page.getByRole("alert")).toContainText("Master 계정");
  await expect(page.getByRole("link", { name: "관리 콘솔" })).toHaveCount(0);
  expect(master.reads).toHaveLength(0);
});

test("Master overview filters, user pagination and Audit empty state", async ({ page, master }) => {
  master.cursor = target;
  await page.goto("/master");
  await expect(page.getByRole("heading", { name: "크레딧 흐름" })).toBeVisible();
  await page.getByLabel("조회 기간").selectOption("7");
  await page.getByLabel("데이터 구분").selectOption("synthetic");
  await expect.poll(() => master.reads.some(r => r.includes("days=7") && r.includes("origin=synthetic"))).toBe(true);
  await page.getByRole("button", { name: "사용자", exact: true }).click();
  await expect(page.getByText("123,456.000001")).toBeVisible();
  await page.getByRole("button", { name: "다음 사용자" }).click();
  await expect.poll(() => master.reads.some(r => r.includes("after="))).toBe(true);
  await page.getByRole("button", { name: "Audit", exact: true }).click();
  await expect(page.getByText("데이터가 없습니다.")).toBeVisible();
});

test("confirmation and synchronous double-submit guard", async ({ page, master }) => {
  let release!: () => void; master.hold = new Promise<void>(resolve => { release = resolve; });
  await page.goto("/master"); await page.getByRole("button", { name: "사용자", exact: true }).click();
  await page.getByRole("button", { name: `사용자 관리 ${target}` }).click();
  await expect(page.getByRole("button", { name: "변경 적용" })).toBeDisabled();
  await page.getByLabel("대상과 변경 내용을 확인했습니다.").check();
  await page.getByRole("button", { name: "변경 적용" }).evaluate((button: HTMLButtonElement) => { button.click(); button.click(); });
  await expect.poll(() => master.bodies.length).toBe(1);
  await expect(page.getByLabel("조치")).toBeDisabled();
  release(); await expect(page.getByRole("status")).toContainText("Audit에 기록");
});

test("failed bonus submission retries same immutable request", async ({ page, master }) => {
  master.commandStatus = 503;
  await page.goto("/master"); await page.getByRole("button", { name: "사용자", exact: true }).click();
  await page.getByRole("button", { name: `사용자 관리 ${target}` }).click();
  await page.getByLabel("조치", { exact: true }).selectOption("bonus_grant");
  await page.getByLabel("보너스 크레딧").fill("10.000001");
  await page.getByLabel("대상과 변경 내용을 확인했습니다.").check();
  await page.getByRole("button", { name: "변경 적용" }).click();
  await expect(page.getByRole("alert")).toContainText("동일 요청");
  expect(master.bodies[0].amount_microcredits).toBe(10000001);
  master.commandStatus = 200;
  await page.getByRole("button", { name: "동일 요청 재시도" }).click();
  await expect(page.getByRole("status")).toContainText("중복 변경하지 않았습니다");
  expect(master.bodies[1]).toEqual(master.bodies[0]);
  await expect(page.getByText("untrusted_raw_error")).toHaveCount(0);
});

for (const status of [403, 503]) test(`safe read error ${status}`, async ({ page, master }) => {
  master.status = status; await page.goto("/master");
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.getByText("untrusted_raw_error")).toHaveCount(0);
});
test("expired Session hides console", async ({ page, master }) => {
  master.status = 401; await page.goto("/master");
  await expect(page.getByRole("button", { name: "Google로 계속하기" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "크레딧 흐름" })).toHaveCount(0);
});
test("late result after logout cannot restore Master data", async ({ page, master, http }) => {
  let release!: () => void; master.readHold = new Promise<void>(resolve => { release = resolve; });
  await page.goto("/master"); await expect.poll(() => master.reads.length).toBeGreaterThan(0);
  await page.getByRole("button", { name: "계정 정보" }).first().click();
  await page.getByRole("button", { name: "로그아웃", exact: true }).click();
  await expect.poll(() => http.logout).toBe(1); release();
  await expect(page.getByRole("button", { name: "Google로 계속하기" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "크레딧 흐름" })).toHaveCount(0);
});
test("self-suspension option disabled", async ({ page, master }) => {
  master.items = [{ ...member, id: user.id, role: "master", plan: "max" }];
  await page.goto("/master"); await page.getByRole("button", { name: "사용자", exact: true }).click();
  await page.getByRole("button", { name: `사용자 관리 ${user.id}` }).click();
  await expect(page.getByRole("option", { name: "사용자 정지" })).toHaveAttribute("disabled", "");
});
test("Audit shows bounded before/after changes", async ({ page, master }) => {
  master.audit = [{ request_id: target, actor_id: user.id, target_id: target, action: "bonus_grant", source: "browser",
    reason_code: "support_adjustment", before: { plan: "pro" }, after: { bonus_microcredits: "10000001" }, created_at: "2025-01-31T00:00:00Z" }];
  await page.goto("/master"); await page.getByRole("button", { name: "Audit", exact: true }).click();
  await expect(page.getByText("보너스: 10.000001")).toBeVisible();
  await expect(page.getByText("고객 지원 조정")).toBeVisible();
});
test("invalid bonus does not send a command", async ({ page, master }) => {
  await page.goto("/master"); await page.getByRole("button", { name: "사용자", exact: true }).click();
  await page.getByRole("button", { name: `사용자 관리 ${target}` }).click();
  await page.getByLabel("조치", { exact: true }).selectOption("bonus_grant");
  await page.getByLabel("보너스 크레딧").fill("-1");
  await page.getByLabel("대상과 변경 내용을 확인했습니다.").check();
  await page.getByRole("button", { name: "변경 적용" }).click();
  await expect(page.getByRole("alert")).toContainText("양수");
  expect(master.bodies).toHaveLength(0);
});
for (const width of [1440, 390, 320]) test(`responsive masked console ${width}`, async ({ page }) => {
  await page.setViewportSize({ width, height: 900 }); await page.goto("/master");
  await expect(page.getByRole("heading", { name: "크레딧 흐름" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await mkdir("../.omo/evidence/issue-148/screens", { recursive: true });
  await page.screenshot({ path: `../.omo/evidence/issue-148/screens/overview-${width}.png`, fullPage: true,
    mask: [page.locator(".creative-account, .master-identity")] });
  await page.getByRole("button", { name: "사용자", exact: true }).click();
  await page.getByRole("button", { name: `사용자 관리 ${target}` }).click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: `../.omo/evidence/issue-148/screens/command-${width}.png`, fullPage: true,
    mask: [page.locator(".creative-account, .master-identity, input")] });
});
