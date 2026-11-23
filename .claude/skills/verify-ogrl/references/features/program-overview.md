# Program overview

`/programs/[programId]`, in `web/src/app/programs/[programId]/page.tsx`. A summary of one program at the evaluation instant.

## Sub-features

- title: system name above, h1 with the program name, "Evaluated at <date>", baseline name.
- control-status: `region "Control status"`, a "Control readiness" card: percent met headline, "N of M controls met", four state links (Met, Gap, Waived, Out of scope) with counts, and a segment bar. Gap is red when above 0. "All controls" links to the unfiltered list.
- requirement-coverage: one row per framework on the baseline, with a covered/gap/contribution/unmapped bar and percent covered.
- gaps: up to 6 gap controls, each showing its first failed condition and linking to the control. "+ N more" appears beyond 6. "View all" goes to `controls?state=gap`. With no gaps, a "Every control on the baseline is met…" message.
- needs-attention: counts for failing tests, expiring evidence, expiring exceptions, open findings, open risks, and agent drafts.
- recent-jobs: the 5 newest jobs: type, status (failed jobs show the error title) with duration, date. "View all" goes to Jobs.

## How to get to it (user POV)

`/` redirects here. Or click Overview or the OGRL logo in the sidebar.

## Driving it

```bash
pnpm drive shot /programs/program--acme-platform-800-171
pnpm drive shot "/programs/program--acme-platform-800-171?at=2026-09-01"
pnpm e2e overview
```

- Metric links: `page.getByRole("region", { name: "Control status" }).getByRole("link", { name: /^Gap/ })`.
- Gap row: `page.getByRole("link", { name: /IAM-01/ })`.
- Fixture expectations for 800-171 today: 16 met, 6 gap, 1 waived, 2 out of scope (25 total).

## Gotchas

- The Gaps card shows its count as a badge beside the title, outside the `CardTitle`, so `getByText("Gaps", { exact: true })` still matches.
- The 800-53 program shares controls with 800-171, but its counts differ. Do not hardcode 800-171 numbers in a test that covers both.
