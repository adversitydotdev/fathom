import { PROGRAM_171, expect, test } from "./fixtures";

test("overview shows metrics, coverage, gaps, attention, jobs", async ({ page, shot }) => {
  await page.goto(`/programs/${PROGRAM_171}`);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("NIST 800-171");
  const status = page.getByRole("region", { name: "Control status" });
  for (const label of ["Met", "Gap", "Waived", "Out of scope"]) {
    await expect(status.getByRole("link", { name: new RegExp(`^${label}`) })).toBeVisible();
  }
  for (const title of ["Requirement coverage", "Gaps", "Needs attention", "Recent jobs"]) {
    await expect(page.getByText(title, { exact: true })).toBeVisible();
  }
  await shot("overview");
});

test("gap metric links to the filtered control list", async ({ page }) => {
  await page.goto(`/programs/${PROGRAM_171}`);
  await page.getByRole("region", { name: "Control status" }).getByRole("link", { name: /^Gap/ }).click();
  await expect(page).toHaveURL(/\/controls\?state=gap$/);
  await expect(page.getByRole("button", { name: /^gap/ })).toHaveAttribute("aria-pressed", "true");
});

test("a gap row opens the control in the side panel", async ({ page }) => {
  await page.goto(`/programs/${PROGRAM_171}`);
  await page.getByRole("link", { name: /IAM-01/ }).click();
  await expect(page).toHaveURL(/\/controls\/control--account-lifecycle$/);
  const panel = page.getByRole("dialog", { name: /IAM-01/ });
  await expect(panel.getByRole("heading", { level: 2 })).toHaveText("Account lifecycle management");
  // The overview stays underneath.
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("NIST 800-171");
  await panel.getByRole("button", { name: "Close panel" }).click();
  await expect(page).toHaveURL(new RegExp(`/programs/${PROGRAM_171}$`));
  await expect(panel).toHaveCount(0);
});

test("?at re-evaluates and is shown", async ({ page }) => {
  await page.goto(`/programs/${PROGRAM_171}?at=2026-09-01`);
  await expect(page.getByText("Evaluated at")).toContainText("2026-09-01");
});
