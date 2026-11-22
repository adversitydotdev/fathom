import { PROGRAM_171, expect, test } from "./fixtures";

const PAGE = `/programs/${PROGRAM_171}/integrations`;

// The mock store lives as long as the dev server, so saved names are unique per run.
const unique = (base: string) => `${base}-${Date.now().toString(36)}`;

test("define an AWS query source: search, pick fields, validate, sample, save", async ({ page, shot }) => {
  await page.goto(PAGE);
  const card = page.getByRole("article", { name: "AWS" });
  const sources = card.getByLabel("AWS query sources");
  await expect(sources.getByText("security-groups@1")).toBeVisible();
  await expect(sources.getByText("ec2.DescribeSecurityGroups")).toBeVisible();

  await card.getByRole("button", { name: "Define a query on AWS" }).click();
  const dialog = page.getByRole("dialog", { name: "New query source on AWS" });
  await dialog.getByLabel(/^Operation/).fill("security groups");
  await dialog.getByRole("button", { name: "Search" }).click();
  await dialog.getByRole("list", { name: "Operations" }).getByRole("button", { name: "Use ec2.DescribeSecurityGroups" }).click();
  const chosen = dialog.getByLabel("Chosen operation");
  await expect(chosen.getByText("ec2Query")).toBeVisible();
  await expect(chosen.getByText("regional")).toBeVisible();

  const name = unique("open-groups");
  await dialog.getByLabel(/^Name/).fill(name);
  await dialog.getByLabel(/^Filters/).fill('[{"Name": "ip-permission.cidr", "Values": ["0.0.0.0/0"]}]');
  await expect(dialog.getByLabel(/^Regions/)).toHaveValue("*");

  const fields = dialog.getByRole("complementary", { name: "Item fields" });
  await dialog.getByRole("textbox", { name: "Path of id" }).click();
  await fields.getByRole("button", { name: "Use GroupId" }).click();
  await dialog.getByRole("textbox", { name: "Path of name" }).click();
  await fields.getByRole("button", { name: "Use GroupName" }).click();
  await fields.getByRole("button", { name: "Use IpPermissions" }).click(); // no row focused: a new row
  await expect(dialog.getByRole("textbox", { name: "Field name 3" })).toHaveValue("ip_permissions");

  const check = dialog.getByRole("region", { name: "Check" });
  await check.getByRole("button", { name: "Validate" }).click();
  await expect(check.getByText("valid", { exact: true })).toBeVisible();
  await expect(check.getByLabel("Item schema")).toContainText("region: string");

  const sample = dialog.getByRole("region", { name: "Dry run" });
  await sample.getByLabel("Connection").selectOption("connection--aws-prod");
  await sample.getByRole("button", { name: "Run sample" }).click();
  await expect(sample.getByText("4 items sampled. Nothing is stored.")).toBeVisible();
  const table = sample.getByRole("table", { name: "Sample items" });
  await expect(table.getByText("sg-0b2bastion").first()).toBeVisible();
  await expect(table.getByText("eu-west-1").first()).toBeVisible();
  await shot("query-editor");

  await dialog.getByRole("button", { name: "Save query source" }).click();
  await expect(dialog).toBeHidden();
  await expect(sources.getByText(`${name}@1`)).toBeVisible();

  await card.getByRole("button", { name: "Write a rule on AWS" }).click();
  const rule = page.getByRole("dialog", { name: "New rule test" });
  await expect(rule.getByLabel("Source").locator("option", { hasText: `${name}@1 (query)` })).toHaveCount(1);
});

test("feedback points at the field, the parameter, and the region", async ({ page }) => {
  await page.goto(PAGE);
  await page.getByRole("button", { name: "Define a query on Okta" }).click();
  const dialog = page.getByRole("dialog", { name: "New query source on Okta" });
  await dialog.getByLabel(/^Operation/).fill("policies");
  await dialog.getByRole("button", { name: "Search" }).click();
  await dialog.getByRole("button", { name: "Use listPolicies" }).click();
  await dialog.getByLabel(/^Name/).fill("password-policies");
  await dialog.getByRole("textbox", { name: "Path of id" }).fill("id");
  await dialog.getByRole("textbox", { name: "Path of name" }).fill("nmae");

  await dialog.getByRole("region", { name: "Check" }).getByRole("button", { name: "Validate" }).click();
  await expect(dialog.getByText("items have no 'nmae'; did you mean 'name'?")).toBeVisible();
  await expect(dialog.getByText("listPolicies needs type")).toBeVisible();
  await expect(dialog.getByRole("textbox", { name: "Path of name" })).toHaveAttribute("aria-invalid", "true");
  await expect(dialog.getByLabel(/^Regions/)).toHaveCount(0); // OpenAPI sources have no regions

  await dialog.getByLabel(/^type/).fill("PASSWORD");
  await dialog.getByRole("textbox", { name: "Path of name" }).fill("name");
  const sample = dialog.getByRole("region", { name: "Dry run" });
  await sample.getByRole("button", { name: "Run sample" }).click();
  await expect(sample.getByText("2 items sampled. Nothing is stored.")).toBeVisible();
  await expect(sample.getByRole("table", { name: "Sample items" }).getByText("Administrators")).toBeVisible();
});

test("a saved query source is a rule source with its own fields", async ({ page }) => {
  await page.goto(`/programs/${PROGRAM_171}/tests`);
  await page.getByRole("button", { name: "New rule test" }).click();
  const dialog = page.getByRole("dialog", { name: "New rule test" });
  await dialog.getByLabel("Source").selectOption("dev.adversity.aws/security-groups@1");
  const fields = dialog.getByRole("complementary", { name: "Fields" });
  await expect(fields.getByRole("button", { name: "Insert region" })).toBeVisible();
  await dialog.getByRole("textbox", { name: "Assert", exact: true }).fill('item.name != "bastion"');
  const preview = dialog.getByRole("region", { name: "Preview" });
  await preview.getByRole("button", { name: "Preview" }).click();
  await expect(preview.getByText("2 of 3 selected items pass")).toBeVisible();
});

test("a query source nothing reads can be removed", async ({ page }) => {
  await page.goto(PAGE);
  const card = page.getByRole("article", { name: "AWS" });
  await card.getByRole("button", { name: "Define a query on AWS" }).click();
  const dialog = page.getByRole("dialog", { name: "New query source on AWS" });
  await dialog.getByLabel(/^Operation/).fill("roles");
  await dialog.getByRole("button", { name: "Search" }).click();
  await dialog.getByRole("button", { name: "Use iam.ListRoles" }).click();
  await expect(dialog.getByLabel("Chosen operation").getByText("global")).toBeVisible();
  const name = unique("roles");
  await dialog.getByLabel(/^Name/).fill(name);
  await dialog.getByRole("textbox", { name: "Path of id" }).fill("RoleId");
  await dialog.getByRole("textbox", { name: "Path of name" }).fill("RoleName");
  await dialog.getByRole("button", { name: "Save query source" }).click();
  await expect(dialog).toBeHidden();

  const sources = card.getByLabel("AWS query sources");
  await expect(sources.getByText(`${name}@1`)).toBeVisible();
  await sources.getByRole("button", { name: `Remove dev.adversity.aws/${name}@1` }).click();
  await sources.getByRole("button", { name: "Confirm" }).click();
  await expect(sources.getByText(`${name}@1`)).toHaveCount(0);
});

test("the assistant drafts a query source into the editor; a person saves it", async ({ page, shot }) => {
  await page.goto(PAGE);
  await page.getByRole("button", { name: "AI", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "OGRL AI Assistant" });
  await drawer.getByRole("textbox").fill("Write a query source for security groups open to the internet");
  await drawer.getByRole("textbox").press("Enter");
  for (const tool of ["search_operations", "describe_operation", "validate_query", "dry_run_query", "propose_query_source"]) {
    await expect(drawer.getByText(tool).first()).toBeVisible();
  }
  await expect(drawer.getByText(/validation pointed at/)).toBeVisible();
  await shot("assistant-query-draft");
  await drawer.getByRole("link", { name: /Draft query source: dev.adversity.aws\/internet-open-groups@1/ }).click();

  const dialog = page.getByRole("dialog", { name: "New query source on AWS" });
  await expect(dialog.getByLabel("Assistant draft")).toContainText("item.rules == []");
  await expect(dialog.getByLabel(/^Name/)).toHaveValue("internet-open-groups");
  await expect(dialog.getByLabel("Chosen operation").getByText("ec2.DescribeSecurityGroups")).toBeVisible();
  await expect(dialog.getByLabel(/^Filters/)).toHaveValue('[{"Name": "ip-permission.cidr", "Values": ["0.0.0.0/0"]}]');
  await expect(dialog.getByRole("textbox", { name: "Path of id" })).toHaveValue("GroupId");

  const check = dialog.getByRole("region", { name: "Check" });
  await check.getByRole("button", { name: "Validate" }).click();
  await expect(check.getByText("valid", { exact: true })).toBeVisible();
  await shot("query-editor-draft");
  await dialog.getByRole("button", { name: "Save query source" }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByLabel("AWS query sources").getByText("internet-open-groups@1")).toBeVisible();

  // Clean up so the next run can draft the same name.
  await page.getByLabel("AWS query sources").getByRole("button", { name: "Remove dev.adversity.aws/internet-open-groups@1" }).click();
  await page.getByLabel("AWS query sources").getByRole("button", { name: "Confirm" }).click();
  await expect(page.getByLabel("AWS query sources").getByText("internet-open-groups@1")).toHaveCount(0);
});
