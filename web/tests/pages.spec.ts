import { expect, test } from "@playwright/test";
import { fixture, mockApi } from "./mock";

test("stock page shows the chart, the business numbers and the scorecard", async ({ page }) => {
  await mockApi(page);
  await page.goto("/stocks/CHENNPETRO");
  await expect(page.getByRole("img", { name: /CHENNPETRO price chart/ })).toBeVisible();
  await expect(page.getByText("ROCE", { exact: true })).toBeVisible();
  const card = fixture("stocks_CHENNPETRO");
  await expect(page.getByRole("heading", { name: `Scorecard · ${card.scorecard.passed} of ${card.scorecard.total}` })).toBeVisible();
  await page.getByRole("button", { name: "1Y" }).click();
  await expect(page.getByRole("button", { name: "1Y" })).toHaveAttribute("aria-pressed", "true");
});

test("stock search finds a stock by symbol", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await page.getByPlaceholder("Find a stock").fill("chenn");
  await page.getByRole("option", { name: /CHENNPETRO/ }).click();
  await expect(page).toHaveURL(/\/stocks\/CHENNPETRO$/);
});

test("before the open lists likely movers on both sides", async ({ page }) => {
  await mockApi(page);
  await page.goto("/before-open");
  const data = fixture("before-open");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(data.guess);
  await page.getByRole("button", { name: /Likely down/ }).click();
  if (data.down.length) await expect(page.getByRole("table")).toContainText(data.down[0].symbol);
});

test("news page shows the test result and the movers", async ({ page }) => {
  await mockApi(page);
  await page.goto("/news");
  await expect(page.getByText(/Tested on one year/)).toBeVisible();
  await page.getByRole("button", { name: /Heavy selling/ }).click();
  await expect(page.getByRole("heading", { name: "What usually happens after news" })).toBeVisible();
});

test("market page shows the backtest against Nifty", async ({ page }) => {
  await mockApi(page);
  await page.goto("/market");
  await expect(page.getByText("Growth per year")).toBeVisible();
  await expect(page.getByRole("img", { name: /model against Nifty/ })).toBeVisible();
});

test("recording a buy sends the order to the server", async ({ page }) => {
  const posts = await mockApi(page);
  await page.goto("/trades");
  const form = page.getByRole("form", { name: "Record a buy" });
  await form.getByLabel("Stock").fill("INFY");
  await form.getByLabel("Price (₹)").fill("1500");
  await form.getByLabel("Quantity").fill("5");
  await form.getByRole("button", { name: "Save buy" }).click();
  await expect(page.getByRole("status")).toContainText("Saved: bought 5 INFY");
  expect(posts[0].path).toBe("trades/buy");
  expect(posts[0].body).toMatchObject({ symbol: "INFY", price: 1500, quantity: 5 });
});
