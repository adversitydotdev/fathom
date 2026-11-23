import { PROGRAM_171, expect, test } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await page.goto(`/programs/${PROGRAM_171}/policies`);
});

test("the toolbar and typed Markdown both format, and the source is Markdown", async ({ page, shot }) => {
  await page.getByRole("button", { name: "New policy" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel(/Name/).fill("Editor Policy");
  const editor = dialog.getByRole("textbox", { name: "Policy text" });
  await editor.click();

  // Familiar path: pick a style, click Bold, click a list button.
  await dialog.getByLabel("Text style").selectOption({ label: "Title" });
  await page.keyboard.type("Editor Policy");
  await page.keyboard.press("Enter");
  await page.keyboard.type("Data is ");
  await dialog.getByRole("button", { name: "Bold" }).click();
  await page.keyboard.type("classified");
  await dialog.getByRole("button", { name: "Bold" }).click();
  await page.keyboard.type(" on creation.");
  await page.keyboard.press("Enter");
  // Explicit Markdown is still honoured as you type.
  await page.keyboard.type("## Rules");
  await page.keyboard.press("Enter");
  await page.keyboard.type("- Label everything");

  await expect(editor.getByRole("heading", { name: "Editor Policy", level: 1 })).toBeVisible();
  await expect(editor.getByRole("heading", { name: "Rules", level: 2 })).toBeVisible();
  await expect(editor.locator("strong")).toHaveText("classified");
  await expect(editor.getByRole("listitem")).toHaveText("Label everything");
  await shot("policy-editor");

  await dialog.getByRole("button", { name: "Markdown" }).click();
  const source = dialog.getByLabel("Policy text (Markdown)");
  await expect(source).toHaveValue(/^# Editor Policy\n\nData is \*\*classified\*\* on creation\.\n\n## Rules\n\n- Label everything/);

  // Editing the source updates the formatted view.
  await source.fill("# Editor Policy\n\n1. First step");
  await dialog.getByRole("button", { name: "Markdown" }).click();
  await expect(editor.locator("ol li")).toHaveText("First step");

  await dialog.getByRole("button", { name: "Create policy" }).click();
  const row = page.locator("tbody tr", { hasText: "Editor Policy" });
  await row.getByRole("button", { name: "Edit Editor Policy" }).click();
  await expect(page.getByRole("dialog").getByRole("textbox", { name: "Policy text" }).locator("ol li")).toHaveText("First step");
  await page.keyboard.press("Escape");
  await row.getByRole("button", { name: "Revoke Editor Policy" }).click();
  await row.getByRole("button", { name: "Confirm" }).click();
  await expect(row).toHaveCount(0);
});

test("editing an existing policy loads its current text", async ({ page, shot }) => {
  const row = page.locator("tbody tr", { hasText: "Information Security Policy" });
  await row.getByRole("button", { name: "Edit Information Security Policy" }).click();
  const editor = page.getByRole("dialog").getByRole("textbox", { name: "Policy text" });
  await expect(editor.getByRole("heading", { name: "Information Security Policy" })).toBeVisible();
  await expect(editor.getByRole("cell", { name: "CISO" })).toBeVisible();
  await expect(editor.getByRole("link", { name: "security team" })).toBeVisible();
  await shot("policy-editor-existing");
});

test("pasted Markdown is formatted, not inserted literally", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.getByRole("button", { name: "New procedure" }).click();
  const editor = page.getByRole("dialog").getByRole("textbox", { name: "Procedure steps" });
  await editor.click();

  await page.evaluate(() => navigator.clipboard.writeText("## Steps\n\n1. Export the access list\n2. Send to **owners**"));
  await page.keyboard.press("ControlOrMeta+V");
  await expect(editor.getByRole("heading", { name: "Steps", level: 2 })).toBeVisible();
  await expect(editor.locator("ol li")).toHaveCount(2);
  await expect(editor.locator("strong")).toHaveText("owners");
});
