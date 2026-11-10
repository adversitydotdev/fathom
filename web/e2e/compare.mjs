#!/usr/bin/env node
// Pixel-diffs two screenshot dirs and writes a markdown report of what changed.
//
//   node e2e/compare.mjs <base-dir> <head-dir> [--out dir] [--url prefix] [--md file]
//
// --out   copies before/after/diff PNGs of changed and new shots into this dir
// --url   URL prefix the markdown uses for images under --out (default: relative paths)
// --md    where to write the markdown (default: stdout)
//
// Locally, to see what your branch changed visually:
//   git worktree add /tmp/base main && (cd /tmp/base/web && pnpm i && pnpm e2e)
//   pnpm compare /tmp/base/web/e2e/.screenshots e2e/.screenshots --out /tmp/shot-diff
import { copyFileSync, existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

import pixelmatch from "pixelmatch";
import { PNG } from "pngjs";

const [baseDir, headDir, ...rest] = process.argv.slice(2);
if (!baseDir || !headDir) {
  console.error("usage: compare <base-dir> <head-dir> [--out dir] [--url prefix] [--md file]");
  process.exit(2);
}
const flag = (n) => {
  const i = rest.indexOf(`--${n}`);
  return i >= 0 ? rest[i + 1] : undefined;
};
const out = flag("out");
const url = flag("url");
const mdFile = flag("md");

/** Only the sweep: one shot per route and theme. Spec shots duplicate it. */
const pngs = (dir) => (existsSync(dir) ? readdirSync(dir).filter((f) => f.startsWith("sweep-") && f.endsWith(".png")).sort() : []);
const base = new Set(pngs(baseDir));
const head = pngs(headDir);

const changed = [];
const added = [];
const removed = [...base].filter((f) => !head.includes(f));
let unchanged = 0;

for (const f of head) {
  if (!base.has(f)) {
    added.push(f);
    continue;
  }
  const a = PNG.sync.read(readFileSync(path.join(baseDir, f)));
  const b = PNG.sync.read(readFileSync(path.join(headDir, f)));
  if (a.width !== b.width || a.height !== b.height) {
    changed.push({ f, pixels: null, size: `${a.width}×${a.height} → ${b.width}×${b.height}` });
    continue;
  }
  const diff = new PNG({ width: a.width, height: a.height });
  // threshold absorbs antialiasing noise; a real change moves far more pixels.
  const pixels = pixelmatch(a.data, b.data, diff.data, a.width, a.height, { threshold: 0.1 });
  if (pixels === 0) {
    unchanged++;
    continue;
  }
  changed.push({ f, pixels, diff });
}

const img = (rel) => (url ? `${url.replace(/\/$/, "")}/${rel}` : rel);
if (out) {
  for (const sub of ["before", "after", "diff"]) mkdirSync(path.join(out, sub), { recursive: true });
  for (const c of changed) {
    copyFileSync(path.join(baseDir, c.f), path.join(out, "before", c.f));
    copyFileSync(path.join(headDir, c.f), path.join(out, "after", c.f));
    if (c.diff) writeFileSync(path.join(out, "diff", c.f), PNG.sync.write(c.diff));
  }
  for (const f of added) copyFileSync(path.join(headDir, f), path.join(out, "after", f));
}

const name = (f) => f.replace(/^sweep-/, "").replace(/\.png$/, "");
const lines = [];
lines.push(
  `**Screenshots:** ${changed.length} changed, ${added.length} new, ${removed.length} removed, ${unchanged} unchanged.`,
);
if (!base.size) lines.push("", "_No baseline yet. It is written on the next push to main._");
for (const c of changed) {
  const what = c.size ? `size ${c.size}` : `${c.pixels.toLocaleString("en-US")} px`;
  lines.push(
    "",
    `<details open><summary><code>${name(c.f)}</code> (${what})</summary>`,
    "",
    "| before | after |" + (c.diff ? " diff |" : ""),
    "|---|---|" + (c.diff ? "---|" : ""),
    `| <img src="${img(`before/${c.f}`)}" width="360"> | <img src="${img(`after/${c.f}`)}" width="360"> |` +
      (c.diff ? ` <img src="${img(`diff/${c.f}`)}" width="360"> |` : ""),
    "",
    "</details>",
  );
}
for (const f of added) {
  lines.push("", `<details open><summary><code>${name(f)}</code> (new)</summary>`, "", `<img src="${img(`after/${f}`)}" width="480">`, "", "</details>");
}
if (removed.length) lines.push("", `Removed: ${removed.map((f) => `\`${name(f)}\``).join(", ")}`);

const md = lines.join("\n") + "\n";
if (mdFile) writeFileSync(mdFile, md);
else process.stdout.write(md);
console.error(`changed=${changed.length} added=${added.length} removed=${removed.length} unchanged=${unchanged}`);
