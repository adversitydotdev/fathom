import { CONTROL, PROGRAM_171, expect, test } from "./fixtures";

test("write a rule by clicking fields, preview it, and save it as a test", async ({ page, shot }) => {
  await page.goto(`/programs/${PROGRAM_171}/tests`);
  await page.getByRole("button", { name: "New rule test" }).click();
  const dialog = page.getByRole("dialog", { name: "New rule test" });

  await dialog.getByLabel(/^Name/).fill("Active Okta users have strong MFA");
  await dialog.getByLabel("Control").selectOption(CONTROL.mfaPrivileged);
  await dialog.getByLabel("Fulfills").selectOption({ label: "Privileged groups require phishing-resistant MFA" });
  await expect(dialog.getByLabel("Source")).toHaveValue("dev.adversity.okta/users@1");

  const fields = dialog.getByRole("complementary", { name: "Fields" });
  await expect(fields.getByText("TOTP, hardware token, or phishing-resistant.")).toBeVisible();
  await dialog.getByRole("textbox", { name: "Select", exact: true }).click();
  await fields.getByRole("button", { name: "Insert status" }).click();
  // The insert moves the caret on the next frame; type only once it has landed.
  await expect(dialog.getByRole("textbox", { name: "Select", exact: true })).toHaveValue("item.status");
  await expect
    .poll(() => dialog.getByRole("textbox", { name: "Select", exact: true }).evaluate((el: HTMLTextAreaElement) => el.selectionStart))
    .toBe("item.status".length);
  await dialog.getByRole("textbox", { name: "Select", exact: true }).pressSequentially(' == "ACTIVE"');
  await dialog.getByRole("textbox", { name: "Assert", exact: true }).click();
  await fields.getByRole("button", { name: "Insert strong_mfa" }).click();
  await expect(dialog.getByRole("textbox", { name: "Select", exact: true })).toHaveValue('item.status == "ACTIVE"');
  await expect(dialog.getByRole("textbox", { name: "Assert", exact: true })).toHaveValue("item.strong_mfa");

  const preview = dialog.getByRole("region", { name: "Preview" });
  await preview.getByRole("button", { name: "Preview" }).click();
  await expect(preview.getByText("2 of 4 selected items pass")).toBeVisible();
  const failing = preview.getByRole("table", { name: "Failing items" });
  await expect(failing.getByText("cy@acme.test")).toBeVisible();
  await expect(failing.getByText("dee@acme.test")).toBeVisible();
  await expect(preview.getByText(/5 items from Okta production/)).toBeVisible();
  await shot("rule-editor-preview");

  await dialog.getByRole("button", { name: "Create test" }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByText("Active Okta users have strong MFA")).toBeVisible();
});

test("the preview names misspelt fields and syntax errors under the expression", async ({ page }) => {
  await page.goto(`/programs/${PROGRAM_171}/tests`);
  await page.getByRole("button", { name: "New rule test" }).click();
  const dialog = page.getByRole("dialog", { name: "New rule test" });
  const preview = dialog.getByRole("region", { name: "Preview" });

  await dialog.getByRole("textbox", { name: "Assert", exact: true }).fill("item.strongmfa");
  await preview.getByRole("button", { name: "Preview" }).click();
  await expect(dialog.getByText("item.strongmfa: the resource has no field 'strongmfa'")).toBeVisible();
  await expect(preview.getByText("error", { exact: true })).toBeVisible();

  await dialog.getByRole("textbox", { name: "Assert", exact: true }).fill("item.strong_mfa ==");
  await preview.getByRole("button", { name: "Preview" }).click();
  await expect(preview.getByText("does not compile", { exact: true })).toBeVisible();
  await expect(dialog.getByRole("textbox", { name: "Assert", exact: true })).toHaveAttribute("aria-invalid", "true");
});

test("an integration card opens the editor on its own source", async ({ page }) => {
  await page.goto(`/programs/${PROGRAM_171}/integrations`);
  await page.getByRole("button", { name: "Write a rule on GitHub" }).click();
  const dialog = page.getByRole("dialog", { name: "New rule test" });
  await expect(dialog.getByLabel("Source")).toHaveValue("dev.adversity.github/repositories@1");
  await expect(dialog.getByRole("complementary", { name: "Fields" }).getByText("default_branch")).toBeVisible();
  await dialog.getByRole("textbox", { name: "Assert", exact: true }).fill("item.private");
  await dialog.getByRole("region", { name: "Preview" }).getByRole("button", { name: "Preview" }).click();
  await expect(dialog.getByText("no snapshot yet")).toBeVisible();
});
