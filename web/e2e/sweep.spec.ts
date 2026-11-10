import { CONTROL, PROGRAM_171, PROGRAM_53, expect, setTheme, test } from "./fixtures";

/**
 * Every built route, in both themes. Fails on a console error or an error
 * page, and leaves a screenshot of each in e2e/.screenshots/sweep-*.png.
 * Add a route here when you add a page.
 */
const ROUTES: [string, string][] = [
  ["overview-171", `/programs/${PROGRAM_171}`],
  ["overview-53", `/programs/${PROGRAM_53}`],
  ["overview-past", `/programs/${PROGRAM_171}?at=2026-09-01`],
  ["controls", `/programs/${PROGRAM_171}/controls`],
  ["controls-gap", `/programs/${PROGRAM_171}/controls?state=gap`],
  ...Object.entries(CONTROL).map(([k, id]): [string, string] => [`control-${k}`, `/programs/${PROGRAM_171}/controls/${id}`]),
];

for (const theme of ["dark", "light"] as const) {
  for (const [name, path] of ROUTES) {
    test(`sweep ${theme} ${name}`, async ({ page, shot }) => {
      const errors: string[] = [];
      page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
      page.on("pageerror", (e) => errors.push(e.message));
      await setTheme(page, theme);
      const res = await page.goto(path);
      expect(res?.status()).toBeLessThan(400);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      await shot(`sweep-${theme}-${name}`);
      expect(errors).toEqual([]);
    });
  }
}
