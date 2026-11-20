# Control detail

`/programs/[programId]/controls/[controlId]`, in `controls/[controlId]/page.tsx`, `run-test-button.tsx`, and `actions.ts`.

## Sub-features

- breadcrumb: `navigation "Breadcrumb"` → Controls (keeps `?at`), then the display id.
- state: a state badge, plus family · type · frequency · library/custom.
- failed-conditions: a `role="status"` panel listing why the control is a gap.
- not-on-baseline: "This control is not on the baseline for <program>."
- statement: `{{ param }}` placeholders render with the implementation's value (highlighted), or as `<label>: unset` in red.
- implementation: status, responsibility, component, owner, narrative, customer responsibility, and the modified timestamp. With no implementation, it shows the "has no implementation" message.
- provider-half: an extra implementation card for each provider component on the system.
- agent-draft: the "Drafted by Compliance agent…" banner when an agent created the implementation.
- required-tests: outcome icon, method · interval · latest result, and the summary when not passing. The Run button appears only when the test has a `run` block and the system has an implementation. Clicking it calls `POST /v1/tests/{id}/runs` → "Queued". On error it shows the problem title inline.
- evidence: icon by method, and a validity pill (expired: red, ≤30 days: amber, otherwise green) relative to the evaluation date.
- exceptions: approver, expiry, and justification. Shown only when exceptions exist.
- maps-to: framework, requirement id and part, relationship, and reviewed or draft icon.

## How to get to it (user POV)

Click a row in the controls list or a gap on the overview.

## Driving it

```bash
P=/programs/program--acme-platform-800-171/controls
pnpm drive shot $P/control--mfa-privileged
pnpm drive aria $P/control--account-lifecycle
pnpm e2e control-detail
```

Fixture controls that cover each branch (`CONTROL` in `e2e/fixtures.ts`):

| Id | Covers |
|---|---|
| `control--account-lifecycle` (IAM-01) | gap from an unset parameter |
| `control--mfa-privileged` (IAM-02) | agent draft, failing test, Run button |
| `control--least-privilege` (IAM-03) | met |
| `control--backups` (RES-01) | waived, exception card |

## Gotchas

- "Exceptions" also matches the sidebar. Scope to `getByRole("main")`.
- After a Run, the mock job stays in server memory and appears in Recent jobs until the server restarts.
- Validity tones depend on `?at`. A past date can turn an expired item green.
