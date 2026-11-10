# App shell

The frame around every program page: `web/src/app/programs/[programId]/layout.tsx`, `components/shell/*`, `components/theme.tsx`.

## Sub-features

- home-redirect: `/` redirects to the first program. With no programs it shows "Create your first program".
- sidebar: Overview and Controls are links. The others are inert (`title="Not built yet"`). The active link has `aria-current="page"`. Links carry `?at`.
- fixtures-badge: `Fixtures · no auth` in the header, only in mock mode.
- program-switcher: a `<select aria-label="Program">` listing programs on the same system. Changing it navigates and keeps `?at`.
- evaluation-date: `<input type="date" aria-label="Evaluation date">` writes `?at=YYYY-MM-DD`. The "Evaluate now" button clears it.
- theme-toggle: `aria-label="Toggle dark mode"`. Dark by default, persisted to `localStorage.theme`, applied as the `dark` class on `<html>`.

## How to get to it (user POV)

Open any program page. Sidebar on the left, header controls top right.

## Driving it

```bash
pnpm drive aria /programs/program--acme-platform-800-171   # banner + navigation "Main"
pnpm e2e shell
```

- Switch program: `page.getByLabel("Program").selectOption("program--acme-platform-800-53")`.
- Set date: `page.getByLabel("Evaluation date").fill("2026-09-01")`. Expect `?at=2026-09-01` in the URL.
- Force a theme before load: `setTheme(page, "light")` from `e2e/fixtures.ts`.

## Gotchas

- `?at` must survive every navigation: sidebar, switcher, breadcrumbs, metric links, row clicks. Check it whenever you add a link.
- In full-page screenshots the sticky sidebar background ends at viewport height. That is how Playwright captures sticky elements, not a layout bug.
- There is no mobile layout yet. The grid is a fixed `13rem` sidebar plus content.
