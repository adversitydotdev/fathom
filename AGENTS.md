# OGRL agent guide

Read `README.md` for what this is, `../ogrl-rfcs/rfcs/` for the language specs (RFC 0001–0002), and `docs/rfcs/` for the application architecture, HTTP API, integrations, and query sources (RFC 0003–0007). RFCs win over code.

## Layout

- `ogrl/`: Python kernel, API (FastAPI), plugin ports (heavy bundle/validation/OSCAL operations backed by `ogrl_rs` from `adversitydotdev/ogrl-rs`). Tests in `tests/`.
- `../ogrl-library/library/`: authoritative standard library (`adversitydotdev/ogrl-library`). Regenerate NIST catalogs with `ogrl import nist`; do not hand-edit generated NIST files.
- `api/openapi.yaml`: the HTTP contract. `web` generates types from it (`pnpm gen:api`).
- `web/`: Next.js UI. Read `web/AGENTS.md` before touching it.

## Definition of done

Work is not done until you have proof it works. "It should work" is not proof.

1. `mise run verify` passes. It runs ruff, pytest, eslint, tsc, and the Playwright suite. CI (`.github/workflows/verify.yml`) runs the same checks and uploads the screenshots as an artifact.
2. UI changes: load the `verify-ogrl` skill (`.claude/skills/verify-ogrl/`). Find the feature file for what you changed, drive it, and look at the screenshots. No screenshot means not verified.
3. New page or route: add it to `web/e2e/sweep.spec.ts`, add or update its feature file, and add a spec for its interactions.
4. Report what you verified and what you could not, with the reason.

## Rules

- Providers stay behind the ports in `ogrl/plugins/ports.py`. Nothing in the kernel or API may import a vendor SDK directly.
- Tests do not call real third-party services. Use an in-memory port implementation, or a local emulator that speaks the vendor's API.
- The web UI never computes control state. It renders what the API returns.
- Fixture data for the UI lives in `web/src/mocks/fixtures/`. The e2e suite and feature map name IDs from it. Change all three together.
