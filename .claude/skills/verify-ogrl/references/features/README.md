# OGRL feature map

A behavior-level inventory of the web UI. Agents use it to decide what to drive and what counts as proof. Humans use it as the regression checklist.

## Baseline preconditions

- Mock mode (`OGRL_API_MOCKING=enabled`). The header shows a `Fixtures · no auth` badge. If it is missing, you are hitting a real API.
- The fixtures' "today" is `2026-11-09` (`FIXTURE_NOW` in `web/src/mocks/fixtures/program.ts`). Dates and expiry tones are relative to it, not to the wall clock.
- Fixture org: Acme, with one system (`system--acme-platform`) and two programs:
  - `program--acme-platform-800-171` ("NIST 800-171", the first program, where `/` redirects)
  - `program--acme-platform-800-53` ("NIST 800-53 moderate")
- Mock writes (e.g. a test run) live in server memory until restart. Run order between specs can matter.

## Proof and skip reporting

- Exercise every entry point the feature file lists, and the success, empty, error, and `?at` (past date) paths the change can affect.
- Mocks count because they sit behind the same `/v1` boundary the real API uses. They stop counting if you bypass a page's data loading.
- Unbuilt sidebar sections render as inert text with `title="Not built yet"`. Say so instead of skipping them silently.

## Full sweep

`pnpm e2e` runs `sweep.spec.ts`, which loads every built route in dark and light themes. Then walk the files below top to bottom.

## Files

- [app-shell](app-shell.md): sidebar, program switcher, evaluation date (`?at`), theme toggle, home redirect.
- [program-overview](program-overview.md): status metrics, requirement coverage, gaps list, needs-attention, recent jobs.
- [controls-list](controls-list.md): controls table with state chips, family filter, search, sort, row navigation.
- [control-detail](control-detail.md): statement and parameters, implementation, agent drafts, tests and Run, evidence validity, exceptions, mappings.
- [api](api.md): the Python API and the mock `/v1` surface, driven with curl and pytest.
