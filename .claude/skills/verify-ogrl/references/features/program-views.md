# Program & organization views

The 11 section views under `web/src/app/programs/[programId]/`:
`requirements`, `tests`, `evidence`, `risks`, `exceptions`, `findings`, `policies`, `systems`, `parties`, `library`, `jobs`.

## Sub-features

- requirements: framework coverage breakdown and filterable table (state chips, family/search, mapped controls carrying `?at`).
- tests: baseline test inventory with pass/fail/error/no-methodology chips, method filter, and inline `Run` button (`POST /v1/tests/{id}/runs`).
- evidence: evidence records with validity status (`valid`, `expiring`, `expired`) evaluated against `?at` (or fixture today), SHA-256 digest prefix, and linked control.
- risks: interactive 5×5 Likelihood × Impact Risk Matrix (Inherent vs. Residual toggle, click cell to filter register) + searchable Risk Register table with inherent/residual scores, treatment, status, owner, milestones, and linked controls.
- exceptions: waivers for the program's system evaluated against `?at`, showing active/expiring/expired badge, approver, linked risk, and justification.
- findings: assessment findings for the program's system with `satisfied` / `not-satisfied` badges, `#obj.` objective ref, observed date, linked control, and narrative.
- policies: adopted/draft/retired policies (with `AgentMark` on agent-authored drafts) and linked procedures with owner, review dates, and control links.
- systems: active system card (`function`, `boundary`, FIPS-199 CIA `information_types`, leveraged `parties`), components inventory, and imported provider responsibility bundles (`GET /v1/providers`).
- parties: organization directory (people, teams, roles, agents with `AgentMark`, organizations) with kind filter chips and ownership counts.
- library: pinned `ogrl-library` version/commit/objects (`GET /v1/library`), public catalog link, installed frameworks, standard vs. custom control counts, and `Pull revision` trigger (`POST /v1/library/pull`).
- jobs: `Render OSCAL 1.2.3`, `Render Narrative SSP` (`POST /v1/programs/{id}/renders`), and `Run Git export` (`POST /v1/exports/git`) triggers, plus full job history table with duration and error details.

## Driving it

```bash
pnpm --dir web e2e program-views
pnpm --dir web e2e sweep
```
