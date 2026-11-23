import { CONTROL, PROGRAM_171, expect, test } from "./fixtures";

const list = `/programs/${PROGRAM_171}/controls`;

test("row click opens the panel over the list, and rows swap it", async ({ page, shot }) => {
  await page.goto(list);
  await page.getByRole("button", { name: "IAM-02", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/controls/${CONTROL.mfaPrivileged}$`));
  const panel = page.getByRole("dialog", { name: /IAM-02/ });
  await expect(panel.getByRole("heading", { level: 2 })).toHaveText("Multi-factor authentication for privileged access");
  await expect(panel.getByText("Required tests")).toBeVisible();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Controls");
  await expect(page.getByRole("row", { name: /IAM-02/ })).toHaveAttribute("aria-current", "true");
  await shot("control-panel");

  // The list stays usable: another row replaces the panel's content.
  await page.getByRole("button", { name: "IAM-03", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/controls/${CONTROL.leastPrivilege}$`));
  await expect(page.getByRole("dialog", { name: /IAM-03/ }).getByRole("heading", { level: 2 })).toHaveText("Least privilege");
  await expect(page.getByRole("dialog")).toHaveCount(1);
});

test("Escape closes the panel back to the list, keeping ?at", async ({ page }) => {
  await page.goto(`${list}?at=2026-09-01`);
  await page.getByRole("button", { name: "IAM-03", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/controls/${CONTROL.leastPrivilege}\\?at=2026-09-01$`));
  await expect(page.getByRole("dialog", { name: /IAM-03/ })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page).toHaveURL(/\/controls\?at=2026-09-01$/);
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("Escape inside a dialog opened from the panel closes only the dialog", async ({ page }) => {
  await page.goto(list);
  await page.getByRole("button", { name: "IAM-01", exact: true }).click();
  const panel = page.getByRole("dialog", { name: /IAM-01/ });
  await panel.getByRole("button", { name: "Edit" }).first().click();
  await expect(page.getByRole("button", { name: "Save changes" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "Save changes" })).toHaveCount(0);
  await expect(panel).toBeVisible();
});

test("browser back closes the panel; forward reopens it", async ({ page }) => {
  await page.goto(list);
  await page.getByRole("button", { name: "IAM-03", exact: true }).click();
  await expect(page.getByRole("dialog", { name: /IAM-03/ })).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(/\/controls$/);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.goForward();
  await expect(page.getByRole("dialog", { name: /IAM-03/ })).toBeVisible();
});

test("Open full page and direct loads render the full control page", async ({ page }) => {
  await page.goto(list);
  await page.getByRole("button", { name: "IAM-03", exact: true }).click();
  await page.getByRole("dialog", { name: /IAM-03/ }).getByRole("link", { name: "Open full page" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Least privilege");
  await expect(page.getByRole("dialog")).toHaveCount(0);

  await page.goto(`/programs/${PROGRAM_171}/controls/${CONTROL.mfaPrivileged}`);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Multi-factor authentication for privileged access");
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("control links elsewhere open the panel too", async ({ page }) => {
  await page.goto(`/programs/${PROGRAM_171}/tests`);
  await page.getByRole("link", { name: "VUL-02" }).first().click();
  await expect(page.getByRole("dialog", { name: /VUL-02/ })).toBeVisible();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Tests");
});

test("list filters survive opening the panel, and changing one closes it", async ({ page }) => {
  // At 1440px the panel covers the filter chips; on a wide screen they stay clickable.
  await page.setViewportSize({ width: 1920, height: 1000 });
  await page.goto(`${list}?state=gap`);
  const rows = page.locator("tbody tr");
  await expect(rows).toHaveCount(6);
  await page.getByRole("button", { name: "IAM-01", exact: true }).click();
  await expect(page.getByRole("dialog", { name: /IAM-01/ })).toBeVisible();
  await expect(rows).toHaveCount(6);
  await expect(page.getByRole("button", { name: /^gap/ })).toHaveAttribute("aria-pressed", "true");

  await page.getByRole("button", { name: /^met/ }).click();
  await expect(page).toHaveURL(/\/controls\?state=met$/);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(rows).toHaveCount(16);
});

test("changing the date on a full control page reloads it as a page", async ({ page }) => {
  await page.goto(`/programs/${PROGRAM_171}/controls/${CONTROL.leastPrivilege}`);
  await page.getByLabel("Evaluation date").fill("2026-09-01");
  await expect(page).toHaveURL(/\?at=2026-09-01$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Least privilege");
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("next/previous and j/k step through the list without leaving the panel", async ({ page }) => {
  await page.goto(`${list}?state=gap`);
  await page.getByRole("button", { name: "CHG-01", exact: true }).click();
  const panel = page.getByRole("dialog");
  await expect(panel).toHaveAccessibleName(/CHG-01/);
  await expect(panel.getByText("1 of 6")).toBeVisible();
  await expect(panel.getByRole("button", { name: "Previous control" })).toBeDisabled();

  await panel.getByRole("button", { name: "Next control" }).click();
  await expect(panel).toHaveAccessibleName(/IAM-01/);
  await expect(panel.getByText("2 of 6")).toBeVisible();

  await page.keyboard.press("j");
  await expect(panel).toHaveAccessibleName(/IAM-02/);
  await page.keyboard.press("k");
  await expect(panel).toHaveAccessibleName(/IAM-01/);
  await expect(page.getByRole("row", { name: /IAM-01/ })).toHaveAttribute("aria-current", "true");

  // Stepping replaces history, so Back still closes the panel in one go.
  await page.goBack();
  await expect(page).toHaveURL(/\/controls\?state=gap$/);
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("the panel leads with tests and evidence", async ({ page }) => {
  await page.goto(list);
  await page.getByRole("button", { name: "IAM-02", exact: true }).click();
  const panel = page.getByRole("dialog", { name: /IAM-02/ });
  const tests = await panel.getByText("Required tests", { exact: true }).boundingBox();
  const statement = await panel.getByText("Statement", { exact: true }).boundingBox();
  expect(tests!.y).toBeLessThan(statement!.y);
});
