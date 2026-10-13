import { expect, test } from "@playwright/test";
import { fixture, mockApi } from "./mock";

test.describe("Today page", () => {
  test("shows the plan, the buy cards and your stocks", async ({ page }) => {
    await mockApi(page);
    await page.goto("/");
    const today = fixture("today");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(today.headline);
    await expect(page.getByText("Market: caution")).toBeVisible();
    for (const item of today.buys) {
      await expect(page.getByRole("link", { name: `${item.symbol}: ${item.tag}` })).toBeVisible();
    }
    await expect(page.getByRole("link", { name: "TESTCO: Hold" })).toBeVisible();
    await expect(page.getByRole("table").first()).toContainText("Missed");
  });

  test("buy card opens the stock page", async ({ page }) => {
    await mockApi(page);
    await page.goto("/");
    const first = fixture("today").buys[0];
    await page.getByRole("link", { name: `${first.symbol}: ${first.tag}` }).click();
    await expect(page).toHaveURL(new RegExp(`/stocks/${first.symbol}$`));
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("CHENNPETRO");
  });

  test("context cards are labelled for context, never as buy signals", async ({ page }) => {
    await mockApi(page);
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Before the open" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "News ideas" })).toBeVisible();
    await expect(page.getByText("for context").first()).toBeVisible();
    await expect(page.getByText("not tested")).toHaveCount(0);
  });

  test("Update data starts the update and shows its progress", async ({ page }) => {
    const posts = await mockApi(page);
    await page.goto("/");
    await page.getByRole("button", { name: "Update data" }).click();
    await expect(page.getByRole("status")).toContainText("Markets: 3 of 11");
    expect(posts).toContainEqual({ path: "jobs", body: { kind: "daily" } });
  });

  test("dark and light mode switch and are remembered", async ({ page }) => {
    await mockApi(page);
    await page.goto("/");
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await page.getByRole("button", { name: "Switch light or dark" }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  });

  test("a server problem is shown with a retry button", async ({ page }) => {
    await mockApi(page);
    // Routes added later win, so this one answers /api/today.
    await page.route("**/api/today**", (route) => route.fulfill({ status: 500, json: { detail: "KeyError: boom" } }));
    await page.goto("/");
    await expect(page.getByRole("alert")).toContainText("KeyError: boom");
    await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
  });
});
