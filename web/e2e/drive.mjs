#!/usr/bin/env node
// Ad-hoc driver for agents and humans. Needs a running server:
//   pnpm e2e:serve            (production build, mock mode, :3200)
// Then:
//   pnpm drive shot <path> [--theme light|dark] [--out file.png] [--width 1440]
//   pnpm drive aria <path> [--theme ...]      accessibility tree as YAML; use it to pick selectors
//   pnpm drive check                          is the server up and hydrating?
// E2E_BASE_URL overrides http://localhost:3200.
import { mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

const BASE = process.env.E2E_BASE_URL ?? "http://localhost:3200";
const SHOTS = path.join(path.dirname(fileURLToPath(import.meta.url)), ".screenshots");

const [cmd, target = "/", ...rest] = process.argv.slice(2);
const flag = (name, dflt) => {
  const i = rest.indexOf(`--${name}`);
  return i >= 0 ? rest[i + 1] : dflt;
};

if (!["shot", "aria", "check"].includes(cmd)) {
  console.error("usage: drive shot|aria <path> [--theme light|dark] [--out file] [--width px] | drive check");
  process.exit(2);
}

const browser = await chromium.launch();
try {
  const theme = flag("theme", "dark");
  const context = await browser.newContext({ viewport: { width: Number(flag("width", 1440)), height: 900 } });
  await context.addInitScript((t) => localStorage.setItem("theme", t), theme);
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));

  const res = await page.goto(new URL(cmd === "check" ? "/" : target, BASE).href).catch((e) => {
    console.error(`cannot reach ${BASE}: ${e.message}\nstart it with: pnpm e2e:serve`);
    process.exit(1);
  });
  // Retried: `/` hydrates then client-redirects, destroying the first context.
  for (let i = 0; ; i++) {
    try {
      await page.locator("html[data-hydrated]").waitFor({ state: "attached", timeout: 15_000 });
      await page.evaluate(() => document.fonts.ready);
      break;
    } catch (e) {
      if (i >= 3) throw e;
      await page.waitForLoadState("load");
    }
  }

  if (cmd === "check") {
    console.log(`ok ${res.status()} ${page.url()}`);
  } else if (cmd === "aria") {
    console.log(await page.locator("body").ariaSnapshot());
  } else {
    mkdirSync(SHOTS, { recursive: true });
    const slug = target.replace(/^\//, "").replace(/[^\w.-]+/g, "_") || "root";
    const out = flag("out", path.join(SHOTS, `drive-${theme}-${slug}.png`));
    await page.screenshot({ path: out, fullPage: true, animations: "disabled" });
    console.log(`${res.status()} ${page.url()}\n${out}`);
  }
  if (errors.length) {
    console.error(`console errors:\n${errors.join("\n")}`);
    process.exitCode = 1;
  }
} finally {
  await browser.close();
}
