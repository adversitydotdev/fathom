import { PROGRAM_171, expect, test } from "./fixtures";

test("AI assistant drawer opens, streams tool trace and gap analysis", async ({ page, shot }) => {
  await page.goto(`/programs/${PROGRAM_171}`);

  await page.getByRole("button", { name: "AI", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "OGRL AI Assistant" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("claude-sonnet-4-5")).toBeVisible();

  await dialog.getByRole("button", { name: /Summarize the open control gaps/ }).click();
  await expect(dialog.getByText("get_program_status")).toBeVisible();
  await expect(dialog.getByText(/IAM-01/)).toBeVisible();
  await shot("agent-drawer");

  await dialog.getByRole("button", { name: "Close AI Assistant" }).click();
  await expect(dialog).toHaveCount(0);
});

test("contextual Draft with AI on policies streams and creates a real draft policy", async ({ page }) => {
  await page.goto(`/programs/${PROGRAM_171}/policies`);

  await page.getByRole("button", { name: "Draft with AI" }).click();
  const dialog = page.getByRole("dialog", { name: "OGRL AI Assistant" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("draft_policy")).toBeVisible();
  await expect(dialog.getByText("Draft policy: AI-Drafted Acceptable Use Policy")).toBeVisible();

  await dialog.getByRole("button", { name: "Close AI Assistant" }).click();
  const row = page.locator("tbody tr", { hasText: "AI-Drafted Acceptable Use Policy" });
  await expect(row).toBeVisible();

  // Clean up mock policy so fixture state remains tidy
  await row.getByRole("button", { name: "Revoke AI-Drafted Acceptable Use Policy" }).click();
  await row.getByRole("button", { name: "Confirm" }).click();
  await expect(page.getByText("AI-Drafted Acceptable Use Policy")).toHaveCount(0);
});

test("1-click Accept draft promotes an agent-authored planned control implementation", async ({ page }) => {
  await page.goto(`/programs/${PROGRAM_171}/controls/control--change-control`);
  await expect(page.getByRole("button", { name: "Accept draft" })).toBeVisible();
  await page.getByRole("button", { name: "Accept draft" }).click();
  await expect(page.getByRole("button", { name: "Accept draft" })).toHaveCount(0);
  await expect(page.locator("dd", { hasText: "implemented" })).toBeVisible();
});
