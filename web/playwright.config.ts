import { defineConfig, devices } from "@playwright/test";

// The tests run the built page (npm run build first) with the server's answers
// replaced by saved examples (tests/fixtures), so they need no data and no Python.
const chromium = process.env.PLAYWRIGHT_CHROMIUM_PATH;

export default defineConfig({
  testDir: "tests",
  timeout: 30_000,
  fullyParallel: true,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:4173",
    trace: "retain-on-failure",
    launchOptions: chromium ? { executablePath: chromium } : {},
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1360, height: 900 } } },
    { name: "phone", use: { ...devices["Pixel 7"] }, testMatch: /phone\.spec\.ts/ },
  ],
  webServer: {
    command: "npx vite preview --port 4173 --strictPort",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: !process.env.CI,
  },
});
