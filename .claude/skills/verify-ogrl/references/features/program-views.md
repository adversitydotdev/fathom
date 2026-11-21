# Program & organization views

The 12 section views under `web/src/app/programs/[programId]/`:
`requirements`, `tests`, `evidence`, `risks`, `exceptions`, `findings`, `policies`, `systems`, `parties`, `integrations`, `library`, `jobs`.

## Sub-features

- **Full CRUD**: Create, edit (with `If-Match` optimistic concurrency), and revoke (two-step confirm) across custom Controls, Implementations (status, responsibility, owner, narrative, parameters), Tests + manual Result recording, Evidence (including S3 file upload), Risks, Exceptions, Findings, Policies & Procedures (including S3 Markdown body upload & adoption), Systems, Components, Parties, and Programs.
- requirements: framework coverage breakdown and filterable table (state chips, family/search, mapped controls carrying `?at`).
- rule editor (`web/src/components/rule-editor.tsx`): `New rule test` on the tests page and `Write a rule` on each integration card open a wide dialog: name, control, optional `Fulfills` (tests of that control without `fulfills_ref`), source (every installed integration resource), interval, `Select` / `Assert` / `Aggregate` CEL textareas, allow-empty checkbox. The right column has `Preview` (`POST /v1/rules/preview`: outcome badge, summary, failing items table, snapshot and params used, sample items; errors and misspelt-field warnings appear under the expression they belong to) above the resource's fields (from `resources[].fields`), which insert `item.<field>` into the focused expression. `Create test` posts an ordinary test with `run.runner: rule`. In mock mode the preview uses `web/src/mocks/cel.ts`, a small CEL subset (no `aggregate`, no macros) over `snapshotItems` in the fixtures; only Okta `users@1` has items, so other sources preview as `no snapshot yet`.
- tests: baseline test inventory with pass/fail/error/no-methodology chips, method filter, inline `Run` button (`POST /v1/tests/{id}/runs`), `Record` button for manual tests (`POST /v1/results`), plus `New test`, `Edit`, and `Revoke`.
- evidence: evidence records with validity status (`valid`, `expiring`, `expired`) evaluated against `?at` (or fixture today), SHA-256 digest prefix, linked control, plus `Add evidence`, `Edit`, and `Revoke`.
- risks: interactive 5×5 Likelihood × Impact Risk Matrix (Inherent vs. Residual toggle, click cell to filter register) + searchable Risk Register table with inherent/residual scores, treatment, status, owner, milestones, linked controls, plus `New risk`, `Edit`, and `Revoke`.
- exceptions: waivers for the program's system evaluated against `?at`, showing active/expiring/expired badge, approver, linked risk, justification, plus `New exception`, `Edit`, and `Revoke`.
- findings: assessment findings for the program's system with `satisfied` / `not-satisfied` badges, `#obj.` objective ref, observed date, linked control, narrative, plus `New finding`, `Edit`, and `Revoke`.
- policies: adopted/draft/retired policies (with `AgentMark` on agent-authored drafts) and linked procedures with owner, review dates, control links, plus `New policy`/`New procedure`, `Edit`, and `Revoke`.
- systems: active system card (`function`, `boundary`, FIPS-199 CIA `information_types`, leveraged `parties`), components inventory, imported provider responsibility bundles (`GET /v1/providers`), plus `New system`, `Edit system`, `New program`, and component CRUD.
- parties: organization directory (people, teams, roles, agents with `AgentMark`, organizations) with kind filter chips, ownership counts, plus `New party`, `Edit`, and `Revoke`.
- integrations (RFC 0005): connections table (state badge `active`/`failing`/`pending`/`disabled`, vendor identity or `last_error`, bound components/systems, `Validate` and `Collect` jobs, `Disable`/`Enable` with `If-Match`, two-step `Remove`), `New connection` dialog (integration, name, manifest config fields, write-only password inputs for secrets via `PUT /v1/connections/{id}/secrets/{name}`, binding checkboxes; `Authentication` select switches to OAuth client ID/secret plus the `/v1/oauth/callback` hint, or to an `IAM role ARN` input for `aws_role`), `Authorize` on OAuth rows (`POST /v1/connections/{id}/oauth/start`, then navigates to the vendor; the spec routes the vendor host), the `External ID` on `aws_role` rows, `Install` dialog (archive URL plus optional SHA-256 → `POST /v1/integrations`, queues an `integration_install` job), installed integration cards (tier badge, collected sources, installed versions with `Enable` for upgrade/rollback via `POST /v1/integrations/{id}/versions/{version}/enable`, pending template updates with `Apply` via `POST /v1/integrations/{id}/template-updates/{test_id}/apply` and `If-Match`, test templates with `Enable` → `POST /v1/integrations/{id}/templates/{name}/enable`), and recent snapshots (complete/incomplete with reason, field-stripping warnings). Fixtures: `integrations`, `connections`, `snapshots` in `web/src/mocks/fixtures/program.ts` (`connection--okta-prod` active, `connection--github-acme` failing, `connection--aws-prod` an `aws_role` with an external ID, one incomplete snapshot; `integrationVersions` gives Okta 1.3.0 and enabled 1.4.0, `templateUpdates` one pending update).
- library: pinned `ogrl-library` version/commit (`GET /v1/library`), public catalog link, installed frameworks, standard vs. custom control counts, and `Pull revision` trigger (`POST /v1/library/pull`).
- jobs: `Render OSCAL 1.2.3`, `Render Narrative SSP` (`POST /v1/programs/{id}/renders`), and `Run Git export` (`POST /v1/exports/git`) triggers, plus full job history table with duration and error details.

## Driving it

```bash
pnpm --dir web e2e program-views
pnpm --dir web e2e crud
pnpm --dir web e2e integrations
pnpm --dir web e2e rule-editor
pnpm --dir web e2e sweep
```
