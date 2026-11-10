import { mkdirSync } from "node:fs";
import path from "node:path";

import { expect, test as base, type Page } from "@playwright/test";

/** IDs from src/mocks/fixtures/program.ts. Keep in sync with the feature map. */
export const PROGRAM_171 = "program--acme-platform-800-171";
export const PROGRAM_53 = "program--acme-platform-800-53";
export const CONTROL = {
  /** gap: parameter review_period unset */
  accountLifecycle: "control--account-lifecycle",
  /** gap: required test failing; implementation drafted by the agent; runnable test */
  mfaPrivileged: "control--mfa-privileged",
  /** met */
  leastPrivilege: "control--least-privilege",
  /** waived, with an exception */
  backups: "control--backups",
};

export const SHOTS_DIR = path.join(__dirname, ".screenshots");

/**
 * `shot(name)` writes a full-page PNG to e2e/.screenshots/<name>.png and
 * attaches it to the report. It is the proof a change renders, not a
 * pixel-diff baseline.
 */
export const test = base.extend<{ shot: (name: string) => Promise<void> }>({
  /** Every `page.goto` waits for hydration, so the first click is never dropped. */
  page: async ({ page }, provide) => {
    const goto = page.goto.bind(page);
    page.goto = async (...args) => {
      const res = await goto(...args);
      await settle(page);
      return res;
    };
    await provide(page);
  },
  shot: async ({ page }, provide, info) => {
    mkdirSync(SHOTS_DIR, { recursive: true });
    await provide(async (name) => {
      await settle(page);
      const file = path.join(SHOTS_DIR, `${name}.png`);
      await page.screenshot({ path: file, fullPage: true, animations: "disabled" });
      await info.attach(name, { path: file, contentType: "image/png" });
    });
  },
});

/** Waits for hydration (see src/components/hydrated.tsx) and webfonts. */
export async function settle(page: Page) {
  // Retried: a page can hydrate and then client-redirect (`/` does), which
  // destroys the context mid-evaluate. Settle on whichever page stays.
  await expect(async () => {
    await expect(page.locator("html[data-hydrated]")).toBeAttached({ timeout: 2_000 });
    await page.evaluate(() => document.fonts.ready);
  }).toPass({ timeout: 15_000 });
}

export async function setTheme(page: Page, theme: "light" | "dark") {
  await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
}

export { expect };
