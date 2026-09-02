import { test, expect, maskedScreenshot, viewports } from "./auth-fixtures";

for (const viewport of viewports) {
  test(`existing workspace layout ${viewport.width}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto("/generate");
    await expect(page.locator(".creative-generate")).toBeVisible();
    await maskedScreenshot(page, `baseline-${viewport.width}`);
  });
}
