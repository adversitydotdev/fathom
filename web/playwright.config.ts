import { defineConfig, devices } from "@playwright/test";

/**
 * Drives a production build in mock mode: `/v1` is answered by src/mocks, so
 * no API or database is needed. A production build, because `next dev`
 * compiles routes on first hit and makes timing flaky. A separate port and
 * dist dir keep it off a running `pnpm dev`. Set E2E_BASE_URL to drive a
 * server you already started instead.
 */
const port = Number(process.env.E2E_PORT ?? 3200);
const desktop = { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } };
const baseURL = process.env.E2E_BASE_URL ?? `http://localhost:${port}`;

export default defineConfig({
  testDir: "e2e",
  outputDir: "e2e/.results",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never", outputFolder: "e2e/.report" }]] : "list",
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  // The sweep runs first, on untouched fixtures: specs write to the mock db
  // (a test run adds a job), which would leak into overview screenshots and
  // make the PR screenshot diff noisy.
  projects: [
    { name: "sweep", testMatch: /sweep\.spec\.ts/, use: desktop },
    { name: "specs", testIgnore: /sweep\.spec\.ts/, dependencies: ["sweep"], use: desktop },
  ],
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
        command: `pnpm build && pnpm start --port ${port}`,
        env: { NEXT_DIST_DIR: ".next-e2e", OGRL_API_MOCKING: "enabled" },
        url: `${baseURL}/v1/programs`,
        reuseExistingServer: !process.env.CI,
        timeout: 240_000,
      },
});
