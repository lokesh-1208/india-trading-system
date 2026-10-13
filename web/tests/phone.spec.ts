import { expect, test } from "@playwright/test";
import { mockApi } from "./mock";

test("on a phone the Today page fits the screen without sideways scrolling", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  const width = await page.evaluate(() => document.documentElement.scrollWidth);
  const screen = await page.evaluate(() => window.innerWidth);
  expect(width).toBeLessThanOrEqual(screen + 1);
});
