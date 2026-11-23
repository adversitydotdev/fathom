# Controls list

`/programs/[programId]/controls`, in `page.tsx` and `controls-table.tsx`. Every control on the program's baseline with its computed state.

## Sub-features

- header: the program name above the title, and "N on the baseline · at <date>".
- state-chips: "All N", then one chip per state with its count. Labels are lowercase in the DOM: `met 16`, `gap 6`, `waived 1`, `out of scope 2`. They write `?state=`. Clicking the active chip clears it. Pressed state is shown with `aria-pressed`.
- family-filter: `<select aria-label="Family">` writes `?family=`.
- search: `searchbox "Search controls"` matches id, name, family, owner, and object id. It is client-side and not in the URL.
- default order: gaps first, then waived, met, out of scope, then by display id.
- sort: Id, Control, State, Implementation, and Owner headers are sort buttons.
- row-click: opens the control detail and keeps `?at`. Rows also expose a button named by display id.
- agent-mark: an "Agent draft" mark on controls whose implementation an agent created.
- empty-state: "No controls match these filters."
- responsive: the Failed condition, Implementation, and Owner columns hide below `lg`. The failed text then moves under the name.

## How to get to it (user POV)

Sidebar → Controls, or an overview metric, or "View all" on the Gaps card.

## Driving it

```bash
pnpm drive aria /programs/program--acme-platform-800-171/controls
pnpm e2e controls
```

- Rows: `page.locator("table tbody tr")`.
- Open a control: `page.getByRole("button", { name: "IAM-03", exact: true }).click()`.
- Read the total from the chip instead of counting rows: `getByRole("button", { name: /^All \d+$/ })`.

## Gotchas

- The table streams in after hydration. Wait for the rows (`toHaveCount`) before reading `.count()`.
- `filter({ hasText: "IAM-03" })` can match more than one row because failed conditions mention other ids. Use the id button.
- State badges render lowercase text (`gap`), CSS-styled.
