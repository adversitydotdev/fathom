import { CONTROL, PROGRAM_171, expect, test } from "./fixtures";

test("full CRUD on risks: create, edit, and revoke", async ({ page }) => {
  await page.goto(`/programs/${PROGRAM_171}/risks`);

  await page.getByRole("button", { name: "New risk" }).click();
  await page.getByLabel(/Name/).fill("Unencrypted staging snapshot");
  await page.getByLabel(/Statement/).fill("Nightly staging snapshots lack KMS encryption.");
  await page.getByRole("button", { name: "Create risk" }).click();

  await expect(page.getByText("Unencrypted staging snapshot")).toBeVisible();

  // Edit the newly created risk
  await page.getByRole("button", { name: "Edit Unencrypted staging snapshot" }).click();
  await page.getByLabel(/Status/).selectOption("treating");
  await page.getByRole("button", { name: "Save changes" }).click();

  const row = page.locator("tbody tr", { hasText: "Unencrypted staging snapshot" });
  await expect(row.getByText("treating")).toBeVisible();

  // Revoke it so fixture state stays clean
  await row.getByRole("button", { name: "Revoke Unencrypted staging snapshot" }).click();
  await row.getByRole("button", { name: "Confirm" }).click();
  await expect(page.getByText("Unencrypted staging snapshot")).toHaveCount(0);
});

test("full CRUD on policies: create adopted policy with markdown and revoke", async ({ page }) => {
  await page.goto(`/programs/${PROGRAM_171}/policies`);

  await page.getByRole("button", { name: "New policy" }).click();
  await page.getByLabel(/Name/).fill("Data Classification Policy");
  await page.getByLabel(/Status/).selectOption("adopted");
  await page.getByLabel(/Policy body/).fill("# Data Classification Policy\n\nClassify all customer data.");
  await page.getByRole("button", { name: "Create policy" }).click();

  const row = page.locator("tbody tr", { hasText: "Data Classification Policy" });
  await expect(row).toBeVisible();
  await expect(row.getByText("adopted").first()).toBeVisible();

  await row.getByRole("button", { name: "Revoke Data Classification Policy" }).click();
  await row.getByRole("button", { name: "Confirm" }).click();
  await expect(page.getByText("Data Classification Policy")).toHaveCount(0);
});

test("full CRUD on parties: create and revoke", async ({ page }) => {
  await page.goto(`/programs/${PROGRAM_171}/parties`);

  await page.getByRole("button", { name: "New party" }).click();
  await page.getByLabel(/Name/).fill("Alex Rivera");
  await page.getByLabel(/Kind/).selectOption("person");
  await page.getByRole("button", { name: "Create party" }).click();

  const row = page.locator("tbody tr", { hasText: "Alex Rivera" });
  await expect(row).toBeVisible();

  await row.getByRole("button", { name: "Revoke Alex Rivera" }).click();
  await row.getByRole("button", { name: "Confirm" }).click();
  await expect(page.getByText("Alex Rivera")).toHaveCount(0);
});

test("edit implementation parameter on control detail", async ({ page }) => {
  await page.goto(`/programs/${PROGRAM_171}/controls/${CONTROL.accountLifecycle}`);
  await page.getByRole("button", { name: "Edit" }).first().click();
  await page.getByLabel(/review period/i).fill("90 days");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("90 days")).toBeVisible();
});

test("full CRUD on findings: create, edit determination, and revoke", async ({ page }) => {
  await page.goto(`/programs/${PROGRAM_171}/findings`);

  await page.getByRole("button", { name: "New finding" }).click();
  await page.getByLabel(/Name/).fill("Missing quarterly sign-off");
  await page.getByLabel(/Narrative/).fill("Q3 review had no approver signature.");
  await page.getByRole("button", { name: "Create finding" }).click();

  const card = page.locator("article", { hasText: "Missing quarterly sign-off" });
  await expect(card).toBeVisible();

  await card.getByRole("button", { name: "Edit Missing quarterly sign-off" }).click();
  await page.getByLabel(/Determination/).selectOption("satisfied");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(card.getByText("satisfied", { exact: true })).toBeVisible();

  await card.getByRole("button", { name: "Revoke Missing quarterly sign-off" }).click();
  await card.getByRole("button", { name: "Confirm" }).click();
  await expect(page.getByText("Missing quarterly sign-off")).toHaveCount(0);
});
