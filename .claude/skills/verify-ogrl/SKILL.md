---
name: verify-ogrl
description: Drive the OGRL web UI in a browser to prove a change works, with screenshots, accessibility snapshots, and Playwright specs. Use after any change under web/, or to regression-sweep the app.
---

# Verify OGRL

Prove UI changes in a real browser against a production build in mock mode. In mock mode `/v1` is answered by `web/src/mocks` (MSW handlers over fixtures), so you need no API, database, or auth.

## Tools (run from `web/`)

| Command | What it does |
|---|---|
| `pnpm e2e` | Builds, starts on :3200, and runs every spec in `e2e/`. Screenshots go to `e2e/.screenshots/`. |
| `pnpm e2e <file or -g "name">` | Run a subset. |
| `pnpm e2e:serve` | Start the same server and leave it running for `drive`. |
| `pnpm drive check` | Is the server up and hydrating? |
| `pnpm drive aria <path>` | Accessibility tree as YAML. Pick selectors from this before writing a spec. |
| `pnpm drive shot <path> [--theme light] [--width 390]` | One full-page screenshot. Prints the file path. |
| `pnpm compare <base-dir> <head-dir> --out <dir>` | Pixel-diff two sweep runs. Writes before/after/diff PNGs and a markdown summary. See the header of `e2e/compare.mjs` for diffing your branch against `main`. |

`mise run verify` from the repo root runs everything, Python and Go included.

In CI, every PR gets one comment with before/after/diff images of each page the PR changed visually, compared against `main`. The images live on the orphan `ci-screenshots` branch. Pushes to `main` refresh that baseline. The sweep project runs before the other specs so their writes to the mock data never leak into screenshots. Keep it that way, or the diff fills with noise.

Port 3100 belongs to `pnpm dev:mock` (see `.claude/launch.json`). e2e uses 3200 so it never reuses a dev server, because `next dev` compiles routes on first hit and makes timing flaky.

## Flow

1. Match the change to the files under `references/features/`. Start with `README.md` if you are unsure which ones apply.
2. Run `pnpm drive aria <path>` on the affected pages to see what is actually rendered.
3. Write or update a spec in `e2e/` that covers every entry point in the feature file, plus the success, empty, error, and `?at` paths the change can affect.
4. Run `pnpm e2e`. **Open the screenshots** with the Read tool and look at them. A passing assertion over a broken layout is still broken.
5. Report which feature files you covered, the screenshot paths, and any path you could not reach and why.

## Proof bar

- Drive the UI the way a user would: links, buttons, selects. Use `page.evaluate` only to read state after the user path ran.
- Prefer role and label selectors (`getByRole`, `getByLabel`). Class selectors break under restyles.
- Wait on observable state, never on sleeps. `e2e/fixtures.ts` makes every `page.goto` wait for `html[data-hydrated]`, because a click before hydration is silently dropped.
- Streamed sections (`Suspense`) can arrive after hydration. Assert on their content before counting rows.
- The sweep fails on any console error. Do not silence it, fix the cause.
- Screenshots are evidence, not pixel baselines. Check them yourself.

## Feature map

[`references/features/`](references/features/). Each file has the same four sections: `Sub-features`, `How to get to it (user POV)`, `Driving it`, `Gotchas`. When you add or change a feature, update its file in the same commit.
