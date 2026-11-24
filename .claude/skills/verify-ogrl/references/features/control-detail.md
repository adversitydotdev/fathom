# Control detail

`/programs/[programId]/controls/[controlId]`. The body is `ControlDetail` in `controls/[controlId]/control-detail.tsx` (variants `page` and `panel`), plus `run-test-button.tsx` and `actions.ts`.

Two ways it renders:

- **Side panel** (soft navigation): any control link or row clicked inside a program opens `@panel/(.)controls/[controlId]` as `dialog "<display id> <name>"` on the right, over the page it came from. The URL changes to the control URL. The heading is an h2; the page underneath keeps its h1. Not modal: the list stays usable and another row swaps the panel. The panel leads with required tests, evidence and exceptions, then statement and implementation (CSS `order` on the cards; the two page columns become `contents`). When the page underneath registered its order (`PanelSequence`: the controls table and the overview gaps), the panel header shows Previous/Next control buttons and "N of M", and `j`/`k` step through; stepping uses `replace`, so Back still closes the panel. "Close panel", Escape (unless a dialog inside is open), or browser back closes it and returns to the opening page. "Open full page" is a plain anchor (full load).
- **Full page** (direct load, refresh, shared link, "Open full page"): breadcrumb and h1, two columns. Changing the date here does a full load, because a soft navigation to a control URL would be intercepted into the panel.

## Sub-features

- breadcrumb (full page only): `navigation "Breadcrumb"` → Controls (keeps `?at`), then the display id.
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
