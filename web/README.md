# OpenGRC web

The screen from [RFC 0003 section 8](../docs/rfcs/0003-application.md). Next.js, TypeScript, Tailwind v4, [Spectrum UI](https://ui.spectrumhq.in/) components, and shadcn/ui on Radix underneath them. It renders what the API returns and never computes status itself.

## Run against fixtures

No API process, no database, no login:

```
pnpm install
pnpm dev:mock
```

`OPENGRC_API_MOCKING=enabled` routes every API call to the [MSW](https://mswjs.io/) handlers in `src/mocks`. Server components resolve them in-process (`getResponse`), and `/v1/*` on the web origin serves the same handlers, so `curl localhost:3000/v1/programs` works too. Set `OPENGRC_MOCK_LATENCY_MS=600` to see loading states.

The fixture program is Acme's `acme-platform` system under NIST 800-171 and an 800-53 subset, with at least one control in each computed state. Control state is canned in `src/mocks/fixtures/program.ts`. Requirement coverage and the summary counts are derived from the fixtures in `src/mocks/kernel.ts` so the numbers agree with the mappings. The mock does not vary data by `?at=`; it echoes the date back.

## Run against the API

```
OPENGRC_API_ORIGIN=http://127.0.0.1:8080 OPENGRC_API_TOKEN=... pnpm dev
```

`/v1` and `/health` are proxied to `OPENGRC_API_ORIGIN`, as the web process does in production.

## The contract

`src/lib/api/schema.d.ts` is generated from [`api/openapi.yaml`](../api/openapi.yaml):

```
pnpm gen:api
```

The client (`src/lib/api/client.ts`) and the fixtures are typed against it, so a contract change that breaks a screen or a fixture fails `pnpm typecheck`.

## Layout

| Path | What |
|---|---|
| `src/app/programs/[programId]` | Overview, controls list, control detail |
| `src/lib/api` | Generated types, typed client, `unwrap` |
| `src/lib/data.ts` | Request-scoped loaders, one per API call |
| `src/components/status.tsx` | Computed-state badges, bars, legends. The only place status colors live |
| `src/components/spectrumui` | Spectrum UI components, copied in and adapted. Each adapted file says what changed |
| `src/components/ui` | shadcn/ui primitives (Radix). Spectrum items depend on these |
| `src/mocks` | Fixtures, MSW handlers, and the dispatcher |

## Components

Spectrum UI is the component source (RFC 0003 section 8). Its registry is configured in `components.json`:

```
pnpm dlx shadcn@latest add @spectrumui/<name>
```

Spectrum builds on shadcn/ui with Radix primitives (`asChild`, `@radix-ui/*`), so shadcn here uses the `radix-nova` style. Do not switch it to the Base UI style. Many Spectrum registry items are fixed demos rather than components with props; for those, copy the pattern into `src/components/spectrumui` and note the source, as `status-badge.tsx` does. Keep shadcn primitives for what Spectrum does not ship, such as `Card`.
