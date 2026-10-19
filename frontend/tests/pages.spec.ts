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

test("stock page shows today's live price beside the last saved close", async ({ page }) => {
  // Sample data: saved close 1,459.90 on 13 Oct, live 1,533.30 on 14 Oct (+5.03%)
  await mockApi(page);
  await page.goto("/stocks/CHENNPETRO");
  const header = page.getByTestId("stock-live");
  await expect(header).toContainText("₹1,533.30");
  await expect(header).toContainText("+5.03%");
  await expect(header).toContainText("live 10:59");
  await expect(header).toContainText("Last saved close ₹1,459.90");
  const levels = page.getByTestId("live-levels");
  await expect(levels).toContainText("above the 20-day line");
  await expect(levels).toContainText("above the buy limit");
  await expect(levels).toContainText("decisions use the close");
  await expect(page.getByTestId("model-as-of")).toContainText("close");
});

test("stock page shows only the saved close when the live price is not newer", async ({ page }) => {
  const live = fixture("live");
  live.prices.CHENNPETRO.time = "2026-10-13T15:30:00+05:30";
  await mockApi(page, { live });
  await page.goto("/stocks/CHENNPETRO");
  await expect(page.getByRole("img", { name: /CHENNPETRO price chart/ })).toBeVisible();
  await expect(page.getByTestId("stock-live")).toHaveCount(0);
  await expect(page.getByTestId("live-levels")).toHaveCount(0);
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

test("news ideas show the test result, without the past-reactions table", async ({ page }) => {
  await mockApi(page);
  await page.goto("/news");
  await expect(page.getByText(/Tested on one year/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "What usually happens after news" })).toHaveCount(0);
});

test("mood and movers show both sides", async ({ page }) => {
  await mockApi(page);
  await page.goto("/movers");
  await expect(page.getByText(/^Mood:/)).toBeVisible();
  await page.getByRole("button", { name: /Heavy selling/ }).click();
  await expect(page.getByRole("button", { name: /Heavy selling/ })).toHaveAttribute("aria-pressed", "true");
});

test("before the open says when the market has already opened", async ({ page }) => {
  await mockApi(page);
  await page.goto("/before-open");
  await expect(page.getByTestId("stage-note")).toContainText("this morning's guesses");
});

test("trades show the gain at live prices", async ({ page }) => {
  await mockApi(page);
  await page.goto("/trades");
  // TESTCO: 10 shares bought at 100, live 106 in the sample data
  await expect(page.getByTestId("open-gain")).toContainText("60");
  await expect(page.getByText("Worth now (live)")).toBeVisible();
});

test("market health lists the weakest scores", async ({ page }) => {
  await mockApi(page);
  await page.goto("/market");
  await expect(page.getByRole("heading", { name: /Avoid: weakest scores/ })).toBeVisible();
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


test("market page shows breadth and sector strength", async ({ page }) => {
  await mockApi(page);
  await page.goto("/market");
  await expect(page.getByRole("heading", { name: "Market breadth" })).toBeVisible();
  await expect(page.getByText("Above their 20-day average")).toBeVisible();
  await expect(page.getByRole("img", { name: /Share of stocks above their averages/ })).toBeVisible();
  const first = fixture("market").sectors[0].industry;
  await expect(page.getByText(first, { exact: true }).first()).toBeVisible();
});


test("market checks show the number behind each check and the date they are for", async ({ page }) => {
  const market = fixture("market");
  market.checks_day = "2026-10-16T00:00:00";
  market.checks[0].detail = "Nifty 23,065 vs 24,310 (-5.1%)";
  await mockApi(page, { market });
  await page.goto("/market");
  await expect(page.getByText("at the Fri, 16 Oct close")).toBeVisible();
  await expect(page.getByText("Nifty 23,065 vs 24,310 (-5.1%)")).toBeVisible();
});

test("a buy or sell price takes any paise value, not only steps of 5 paise", async ({ page }) => {
  const posts = await mockApi(page);
  await page.goto("/trades");
  const form = page.getByRole("form", { name: "Record a buy" });
  await form.getByLabel("Stock").fill("KARURVYSYA");
  await form.getByLabel("Price (₹)").fill("362.76");
  await form.getByLabel("Quantity").fill("81");
  expect(await form.getByLabel("Price (₹)").evaluate((input: HTMLInputElement) => input.validity.valid)).toBe(true);
  await form.getByRole("button", { name: "Save buy" }).click();
  await expect(page.getByRole("status")).toContainText("Saved: bought 81 KARURVYSYA");
  expect(posts[0].body).toMatchObject({ symbol: "KARURVYSYA", price: 362.76, quantity: 81 });
});
