import { CONTROL, PROGRAM_171, expect, test } from "./fixtures";

const url = (id: string) => `/programs/${PROGRAM_171}/controls/${id}`;

test("gap from an unset parameter", async ({ page, shot }) => {
  await page.goto(url(CONTROL.accountLifecycle));
  await expect(page.getByRole("status").filter({ hasText: "review_period" })).toBeVisible();
  await expect(page.getByText("review period: unset")).toBeVisible();
  await shot("control-unset-param");
});

test("agent-drafted implementation with a failing test that can be run", async ({ page, shot }) => {
  await page.goto(url(CONTROL.mfaPrivileged));
  await expect(page.getByText("Drafted by")).toContainText("Compliance agent");
  await expect(page.getByText("2 of 14 privileged users")).toBeVisible();
  await shot("control-agent-draft");
  await page.getByRole("button", { name: "Run" }).first().click();
  await expect(page.getByText("Queued").first()).toBeVisible();
});

test("waived control shows its exception", async ({ page, shot }) => {
  await page.goto(url(CONTROL.backups));
  await expect(page.getByRole("main").getByText("Exceptions", { exact: true })).toBeVisible();
  await expect(page.getByText(/Approved by/)).toBeVisible();
  await shot("control-waived");
});

test("breadcrumb returns to the list", async ({ page }) => {
  await page.goto(url(CONTROL.leastPrivilege));
  await page.getByRole("navigation", { name: "Breadcrumb" }).getByRole("link", { name: "Controls" }).click();
  await expect(page).toHaveURL(new RegExp(`/programs/${PROGRAM_171}/controls$`));
});
