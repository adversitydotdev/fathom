import { PROGRAM_171, expect, test } from "./fixtures";

test("requirements page lists coverage and filters by state", async ({ page }) => {
  await page.goto(`/programs/${PROGRAM_171}/requirements`);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Requirements");
  await expect(page.getByText("NIST SP 800-171 Revision 3").first()).toBeVisible();
  await page.getByRole("button", { name: /^gap /i }).click();
  await expect(page.locator("tbody tr").first()).toBeVisible();
});

test("tests page lists outcomes and triggers a test run", async ({ page }) => {
  await page.goto(`/programs/${PROGRAM_171}/tests`);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Tests");
  await expect(page.getByText("Privileged groups require phishing-resistant MFA")).toBeVisible();
  const row = page.locator("tbody tr", { hasText: "Privileged groups require phishing-resistant MFA" });
  await row.getByRole("button", { name: "Run" }).click();
  await expect(row.getByText("Queued")).toBeVisible();
});

test("evidence page evaluates validity against ?at", async ({ page }) => {
  await page.goto(`/programs/${PROGRAM_171}/evidence?at=2026-09-01`);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Evidence");
  await expect(page.getByText("2026-09-01")).toBeVisible();
  await expect(page.getByText("Weekly log review, 2026-W43")).toBeVisible();
});

test("risks page renders 5x5 matrix and filters register by cell", async ({ page }) => {
  await page.goto(`/programs/${PROGRAM_171}/risks`);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Risks");
  await expect(page.getByLabel("Risk matrix")).toBeVisible();
  await expect(page.getByText("Restore from backup not recently tested")).toBeVisible();
  // Click cell (Likelihood 3, Impact 4) -> filters to the single risk at 3x4
  await page.getByRole("button", { name: /Likelihood 3 .*, Impact 4 .*: 1 risks/ }).click();
  await expect(page.locator("tbody tr")).toHaveCount(1);
  await expect(page.getByText("Restore from backup not recently tested")).toBeVisible();
  await page.getByRole("button", { name: /Clear cell/ }).click();
  await expect(page.locator("tbody tr")).toHaveCount(3);
});

test("exceptions, findings, and policies pages render fixture records", async ({ page }) => {
  await page.goto(`/programs/${PROGRAM_171}/exceptions`);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Exceptions");
  await expect(page.getByText("Encrypted backups")).toBeVisible();
  await expect(page.getByText("Priya Shah")).toBeVisible();

  await page.goto(`/programs/${PROGRAM_171}/findings`);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Findings");
  await expect(page.getByText("Audit review records incomplete for October")).toBeVisible();

  await page.goto(`/programs/${PROGRAM_171}/policies`);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Policies");
  await expect(page.getByText("Information Security Policy").first()).toBeVisible();
  await expect(page.getByText("Production Change Control Policy")).toBeVisible();
  await expect(page.getByText("Quarterly Access Certification Runbook")).toBeVisible();
});

test("systems and parties pages render org inventory and provider bundles", async ({ page }) => {
  await page.goto(`/programs/${PROGRAM_171}/systems`);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Systems");
  await expect(page.getByRole("heading", { level: 2, name: "Acme Platform" })).toBeVisible();
  await expect(page.getByText("Okta Workforce Identity Responsibility Matrix")).toBeVisible();
  await expect(page.getByText("AWS Shared Responsibility Matrix (us-east-1)")).toBeVisible();

  await page.goto(`/programs/${PROGRAM_171}/parties`);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Parties");
  await expect(page.getByText("Compliance agent")).toBeVisible();
  await page.getByRole("button", { name: /^team /i }).click();
  await expect(page.locator("tbody tr")).toHaveCount(2);
});

test("library page displays pin and queues a library pull", async ({ page }) => {
  await page.goto(`/programs/${PROGRAM_171}/library`);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Library");
  await expect(page.getByText("v0.2.0")).toBeVisible();
  await page.getByRole("button", { name: "Pull revision" }).click();
  await expect(page.getByText("Queued")).toBeVisible();
});

test("jobs page queues OSCAL render, Narrative SSP, and Git export", async ({ page }) => {
  await page.goto(`/programs/${PROGRAM_171}/jobs`);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Jobs");
  await expect(page.getByText("job--0193-git-export")).toBeVisible();

  const actions = page.getByLabel("Exports and renders");
  await actions.getByRole("button", { name: "Render OSCAL 1.2.3" }).click();
  await actions.getByRole("button", { name: "Render Narrative SSP" }).click();
  await actions.getByRole("button", { name: "Run Git export" }).click();
  await expect(actions.getByText("Queued")).toHaveCount(3);
});
