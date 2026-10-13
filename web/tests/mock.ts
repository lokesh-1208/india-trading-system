// Answer every /api call from the saved examples in tests/fixtures.
import { Page, Route } from "@playwright/test";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const folder = join(dirname(fileURLToPath(import.meta.url)), "fixtures");
export const fixture = (name: string) => JSON.parse(readFileSync(join(folder, `${name}.json`), "utf-8"));

export async function mockApi(page: Page, overrides: Record<string, unknown> = {}) {
  const posts: { path: string; body: unknown }[] = [];
  await page.route("**/api/**", async (route: Route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/api\//, "");
    if (route.request().method() === "POST") {
      posts.push({ path, body: route.request().postDataJSON() });
      if (path in overrides) return route.fulfill({ json: overrides[path] });
      if (path === "jobs") {
        return route.fulfill({ json: { running: true, kind: "daily", label: "Update data", step: "Markets",
          done: 3, total: 11, message: null, error: null, finished: null, seconds: 2 } });
      }
      if (path.startsWith("trades/")) return route.fulfill({ json: fixture("trades") });
      return route.fulfill({ status: 404, json: { detail: "not found" } });
    }
    if (path in overrides) return route.fulfill({ json: overrides[path] });
    let name = path.replace(/\//g, "_");
    if (path.startsWith("stocks/") && path.endsWith("/prices")) name = "stocks_CHENNPETRO_prices_days_126";
    else if (path.startsWith("stocks/") && path.endsWith("/reports")) name = "stocks_CHENNPETRO_reports";
    else if (path.startsWith("stocks/")) name = "stocks_CHENNPETRO";
    if (path === "jobs") return route.fulfill({ json: fixture("status").job });
    try {
      return route.fulfill({ json: fixture(name) });
    } catch {
      return route.fulfill({ status: 404, json: { detail: `no fixture for ${path}` } });
    }
  });
  return posts;
}
