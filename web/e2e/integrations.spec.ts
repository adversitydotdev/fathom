import { PROGRAM_171, expect, test } from "./fixtures";

const PAGE = `/programs/${PROGRAM_171}/integrations`;

test("integrations page lists connections, installed packages, and snapshots", async ({ page, shot }) => {
  await page.goto(PAGE);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Integrations");

  const connections = page.getByRole("region", { name: "Connections" });
  const okta = connections.locator("tr", { hasText: "Okta production" });
  await expect(okta.getByText("active")).toBeVisible();
  await expect(okta.getByText("acme.okta.com as svc-ogrl")).toBeVisible();
  await expect(okta.getByText("Okta Workforce Identity")).toBeVisible();
  const github = connections.locator("tr", { hasText: "GitHub acme-eng" });
  await expect(github.getByText("failing")).toBeVisible();
  await expect(github.getByText(/permission_denied/)).toBeVisible();

  const installed = page.getByRole("region", { name: "Installed integrations" });
  await expect(installed.getByRole("heading", { level: 2, name: "Okta" })).toBeVisible();
  await expect(installed.getByText("first-party")).toBeVisible();
  await expect(installed.getByText("users@1")).toBeVisible();

  const snapshots = page.getByRole("region", { name: "Recent snapshots" });
  await expect(snapshots.getByText("dev.adversity.okta/users@1")).toBeVisible();
  await expect(snapshots.getByText("rate limited after page 3")).toBeVisible();
  await expect(snapshots.getByText("removed undeclared fields: credentials")).toBeVisible();
  await shot("integrations");
});

test("sidebar links to integrations", async ({ page }) => {
  await page.goto(`/programs/${PROGRAM_171}`);
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Integrations" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Integrations");
});

test("validate and collect queue jobs", async ({ page }) => {
  await page.goto(PAGE);
  const row = page.getByRole("region", { name: "Connections" }).locator("tr", { hasText: "Okta production" });
  await row.getByRole("button", { name: "Validate Okta production" }).click();
  await expect(row.getByText("Validation queued")).toBeVisible();
  await row.getByRole("button", { name: "Collect Okta production" }).click();
  await expect(row.getByText("Collection queued")).toBeVisible();
});

test("new connection writes config, secrets, and bindings", async ({ page, shot }) => {
  await page.goto(PAGE);
  await page.getByRole("button", { name: "New connection" }).click();
  const dialog = page.getByRole("dialog", { name: "New connection" });
  await dialog.getByLabel("Integration").selectOption("dev.adversity.okta");
  await dialog.getByLabel("Name").fill("Okta staging");
  await dialog.getByLabel("Okta domain").fill("acme-staging.okta.com");
  const secret = dialog.getByLabel("Read-only API token");
  await expect(secret).toHaveAttribute("type", "password");
  await secret.fill("00a-very-secret-token");
  await dialog.getByLabel("Okta Workforce Identity").check();
  await shot("integrations-new-connection");
  await dialog.getByRole("button", { name: "Connect" }).click();
  await expect(dialog).toBeHidden();

  const row = page.getByRole("region", { name: "Connections" }).locator("tr", { hasText: "Okta staging" });
  await expect(row.getByText("pending")).toBeVisible();
  await expect(row.getByText("Not validated")).toBeVisible();
  await expect(page.getByText("00a-very-secret-token")).toHaveCount(0);
});

test("a template becomes a test", async ({ page }) => {
  await page.goto(PAGE);
  await page.getByRole("button", { name: "Enable Production branches require review and passing checks" }).click();
  await expect(page.getByRole("region", { name: "Installed integrations" }).getByText("Enabled")).toBeVisible();
  await page.goto(`/programs/${PROGRAM_171}/tests`);
  await expect(page.getByText("Production branches require review and passing checks")).toBeVisible();
});

test("disable and remove a connection", async ({ page }) => {
  await page.goto(PAGE);
  const region = page.getByRole("region", { name: "Connections" });
  const row = region.locator("tr", { hasText: "GitHub acme-eng" });
  await row.getByRole("button", { name: "Disable GitHub acme-eng" }).click();
  await expect(row.getByText("disabled")).toBeVisible();
  await expect(row.getByRole("button", { name: "Collect GitHub acme-eng" })).toBeDisabled();
  await row.getByRole("button", { name: "Remove GitHub acme-eng" }).click();
  await row.getByRole("button", { name: "Confirm" }).click();
  await expect(region.getByText("GitHub acme-eng")).toHaveCount(0);
});
