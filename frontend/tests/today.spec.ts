import { expect, test } from "@playwright/test";
import { fixture, mockApi } from "./mock";

test.describe("Today page", () => {
  test("shows the plan, the buy cards and your stocks", async ({ page }) => {
    await mockApi(page);
    await page.goto("/");
    const today = fixture("today");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(today.headline);
    await expect(page.getByText("Market: caution")).toBeVisible();
    await expect(page.getByTestId("list-explain")).toHaveText(today.explain);
    for (const item of today.buys) {
      await expect(page.getByRole("link", { name: `${item.symbol}: ${item.tag}` })).toBeVisible();
    }
    await expect(page.getByRole("link", { name: "TESTCO: Hold" })).toBeVisible();
    await page.getByRole("tab", { name: /Week tracker/ }).click();
    await expect(page.locator("#week table")).toContainText("Missed");
    await expect(page.getByTestId("next-list")).toContainText("Fri, 9 Oct");
    await expect(page.getByTestId("market-checks")).toContainText("1 more not known yet");
    await expect(page.getByTestId("missed-days")).toContainText("Mon, 12 Oct");
  });

  test("live prices show where each stock is now against its limit", async ({ page }) => {
    await mockApi(page);
    await page.goto("/");
    await expect(page.getByTestId("live-status")).toContainText("Live prices, updated every minute");
    const chennpetro = page.getByRole("link", { name: "CHENNPETRO: Buy" });
    await expect(chennpetro).toContainText("Above limit now");
    await expect(chennpetro).toContainText("do not chase");
    await expect(page.getByRole("link", { name: "KOTAKBANK: Buy" })).toContainText("In range now");
    await expect(page.getByRole("link", { name: "TESTCO: Hold" })).toContainText("live ₹106.00");
    await page.getByRole("tab", { name: /Week tracker/ }).click();
    await expect(page.locator("#week table")).toContainText("back in range");
  });

  test("the money plan says how much to put in from the cash you have", async ({ page }) => {
    await mockApi(page);
    await page.goto("/");
    const plan = page.getByTestId("money-plan");
    await expect(plan).toContainText("Put in now: ₹28,501");
    await expect(page.getByTestId("order-CHENNPETRO").getByRole("cell").nth(1)).toHaveText("9");
    await expect(plan).toContainText("Keep ₹15,059 for the 1 empty place");
  });

  test("buy card opens the stock page", async ({ page }) => {
    await mockApi(page);
    await page.goto("/");
    const first = fixture("today").buys[0];
    await page.getByRole("link", { name: `${first.symbol}: ${first.tag}` }).click();
    await expect(page).toHaveURL(new RegExp(`/stocks/${first.symbol}$`));
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("CHENNPETRO");
  });

  test("Today keeps only what you act on; context lives on the Market page", async ({ page }) => {
    await mockApi(page);
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Market mood" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "News ideas" })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: /Avoid/ })).toHaveCount(0);
    await expect(page.getByText("not tested")).toHaveCount(0);
  });

  test("the top bar has three places and live index values", async ({ page }) => {
    await mockApi(page);
    await page.goto("/");
    const nav = page.getByRole("navigation", { name: "Pages" });
    await expect(nav.getByRole("link")).toHaveText(["Today", "Market", "Stocks & trades"]);
    await expect(page.locator(".strip")).toContainText("22,626.55");
    await nav.getByRole("link", { name: "Market" }).click();
    await expect(page).toHaveURL(/\/market$/);
    await page.getByRole("navigation", { name: "Market sections" }).getByRole("link", { name: "News ideas" }).click();
    await expect(page.getByText(/Tested on one year/)).toBeVisible();
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


test.describe("Before 9:15 am", () => {
  test.use({ timezoneId: "Asia/Kolkata" });
  test("the Today page shows the before-the-open card", async ({ page }) => {
    await page.clock.setFixedTime(new Date("2026-10-14T08:45:00+05:30"));
    await mockApi(page);
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Before the open" })).toBeVisible();
  });
});

test("after Monday the page says no buys until the next list, and warns about size", async ({ page }) => {
  const today = fixture("today");
  today.buys = [];
  today.buy_window = { open: false, day: "2026-10-12T00:00:00", next: "2026-10-19T00:00:00" };
  today.money_plan = { ...today.money_plan, buys: [], spend: 0,
    note: "No new buys until Mon 19 Oct: the model buys only at the first open of the week. Keep the cash until then.",
    warning: "Your stocks cost ₹161,971, more than your trading money ₹100,000." };
  today.holds[0].size_vs_plan = 3.01;
  await mockApi(page, { today });
  await page.goto("/");
  await expect(page.locator("#buy")).toContainText("No buys until Mon, 19 Oct");
  await expect(page.getByTestId("money-warning")).toContainText("more than your trading money");
  await expect(page.getByTestId("oversized")).toContainText("3.0× today's place size");
});


test("best by sector is a grid of sector cards; a card opens the full list in a side panel", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  const today = fixture("today");
  // The buy cards come first; the sector list does not push them down.
  await expect(page.getByRole("tab", { name: /This week's buys/ })).toHaveAttribute("aria-selected", "true");
  await page.getByRole("tab", { name: /Best by sector/ }).click();
  const first = today.sectors[0];
  await page.getByRole("button", { name: new RegExp(`^${first.industry}:`) }).click();
  const panel = page.getByRole("dialog", { name: first.industry });
  await expect(panel).toBeVisible();
  await expect(panel.locator("table")).toContainText(first.stocks[0].symbol);
  await page.keyboard.press("Escape");
  await expect(panel).toHaveCount(0);
});

test("your stocks show how far each one is above its exit line", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  const row = page.getByRole("link", { name: "TESTCO: Hold" });
  await expect(row).toContainText("Exit line");
  await expect(row).toContainText(/% (above|below)/);
});

test("every holding shows all its figures in a short card; sells come first; a long list scrolls in its box", async ({ page }) => {
  const today = fixture("today");
  const base = today.holds[0];
  today.holds = [
    ...["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"].map((symbol) => ({ ...base, symbol })),
    { ...base, symbol: "BIGONE", size_vs_plan: 2.18 },
    { ...base, symbol: "SELLME", action: "SELL", reason: "2 closes below the 20-day line" },
  ];
  await mockApi(page, { today });
  await page.goto("/");
  await expect(page.getByTestId("mine-summary")).toContainText("8 stocks · 1 to sell · 1 bigger than the plan");
  // Nothing is folded away: every card has its exit line and GTT stop
  const cards = page.locator("#mine .hold-row");
  await expect(cards).toHaveCount(8);
  for (const symbol of ["AAA", "FFF", "BIGONE"]) {
    const card = page.getByRole("link", { name: `${symbol}: Hold` });
    await expect(card).toContainText("Exit line");
    await expect(card).toContainText("GTT stop");
  }
  await expect(cards.first()).toHaveAttribute("aria-label", "SELLME: Sell");
  await expect(page.getByRole("link", { name: "BIGONE: Hold" }).getByTestId("oversized")).toContainText("2.2× today's place size");
  // Each card stays short (two lines), and a long list scrolls inside its box
  const box = await page.getByRole("link", { name: "AAA: Hold" }).boundingBox();
  expect(box!.height).toBeLessThan(110);
  await expect(page.locator(".mine-list")).toHaveClass(/is-long/);
});
