import { CONTROL, PROGRAM_171, PROGRAM_53, expect, test } from "./fixtures";

test("home redirects to the first program", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(new RegExp(`/programs/${PROGRAM_171}$`));
});

test("mock mode shows the fixtures badge", async ({ page }) => {
  await page.goto(`/programs/${PROGRAM_171}`);
  await expect(page.getByText("Fixtures · no auth")).toBeVisible();
});

test("sidebar marks the current page and navigates", async ({ page }) => {
  await page.goto(`/programs/${PROGRAM_171}`);
  const nav = page.getByRole("navigation", { name: "Main" });
  await expect(nav.getByRole("link", { name: "Overview" })).toHaveAttribute("aria-current", "page");
  await nav.getByRole("link", { name: "Controls" }).click();
  await expect(page).toHaveURL(new RegExp(`/programs/${PROGRAM_171}/controls$`));
  await expect(nav.getByRole("link", { name: "Controls" })).toHaveAttribute("aria-current", "page");
  // All program and organization sections are wired routes.
  await nav.getByRole("link", { name: "Risks" }).click();
  await expect(page).toHaveURL(new RegExp(`/programs/${PROGRAM_171}/risks$`));
  await expect(nav.getByRole("link", { name: "Risks" })).toHaveAttribute("aria-current", "page");
});

test("program switcher changes program and keeps ?at", async ({ page }) => {
  await page.goto(`/programs/${PROGRAM_171}?at=2026-09-01`);
  await page.getByLabel("Program").selectOption(PROGRAM_53);
  await expect(page).toHaveURL(new RegExp(`/programs/${PROGRAM_53}\\?at=2026-09-01$`));
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("NIST 800-53 moderate");
});

test("evaluation date sets and clears ?at, and sidebar links carry it", async ({ page }) => {
  await page.goto(`/programs/${PROGRAM_171}/controls/${CONTROL.leastPrivilege}`);
  await page.getByLabel("Evaluation date").fill("2026-09-01");
  await expect(page).toHaveURL(/\?at=2026-09-01$/);
  await expect(page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Controls" })).toHaveAttribute(
    "href",
    `/programs/${PROGRAM_171}/controls?at=2026-09-01`,
  );
  await page.getByLabel("Evaluate now").click();
  await expect(page).not.toHaveURL(/at=/);
});

test("theme toggle flips and persists", async ({ page }) => {
  await page.goto(`/programs/${PROGRAM_171}`);
  const html = page.locator("html");
  await expect(html).toHaveClass(/dark/);
  await page.getByLabel("Toggle dark mode").click();
  await expect(html).not.toHaveClass(/dark/);
  await page.reload();
  await expect(html).not.toHaveClass(/dark/);
});
