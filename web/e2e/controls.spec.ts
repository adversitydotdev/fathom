import { PROGRAM_171, expect, test } from "./fixtures";

const rows = (page: import("@playwright/test").Page) => page.locator("table tbody tr");

test("lists baseline controls, gaps first", async ({ page, shot }) => {
  await page.goto(`/programs/${PROGRAM_171}/controls`);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Controls");
  await expect(rows(page).first()).toContainText("gap");
  await shot("controls");
});

test("state chips filter and write ?state", async ({ page }) => {
  await page.goto(`/programs/${PROGRAM_171}/controls`);
  const all = Number((await page.getByRole("button", { name: /^All \d+$/ }).textContent())!.replace(/\D/g, ""));
  await expect(rows(page)).toHaveCount(all);
  await page.getByRole("button", { name: /^waived/ }).click();
  await expect(page).toHaveURL(/state=waived/);
  await expect(rows(page)).not.toHaveCount(all);
  for (const row of await rows(page).all()) await expect(row).toContainText("waived");
  // Clicking the active chip clears it.
  await page.getByRole("button", { name: /^waived/ }).click();
  await expect(page).not.toHaveURL(/state=/);
  await expect(rows(page)).toHaveCount(all);
});

test("family filter writes ?family", async ({ page }) => {
  await page.goto(`/programs/${PROGRAM_171}/controls`);
  await page.getByLabel("Family").selectOption("Identity and access");
  await expect(page).toHaveURL(/family=Identity\+and\+access/);
  for (const row of await rows(page).all()) await expect(row).toContainText("Identity and access");
});

test("search narrows rows; no match shows the empty state", async ({ page }) => {
  await page.goto(`/programs/${PROGRAM_171}/controls`);
  const search = page.getByLabel("Search controls");
  await search.fill("IAM-02");
  await expect(rows(page)).toHaveCount(1);
  await expect(rows(page).first()).toContainText("Multi-factor authentication");
  await search.fill("zzz-nothing");
  await expect(page.getByText("No controls match these filters.")).toBeVisible();
});

test("row click opens the control and keeps ?at", async ({ page }) => {
  await page.goto(`/programs/${PROGRAM_171}/controls?at=2026-09-01`);
  await page.getByRole("button", { name: "IAM-03", exact: true }).click();
  await expect(page).toHaveURL(/\/controls\/control--least-privilege\?at=2026-09-01$/);
});
