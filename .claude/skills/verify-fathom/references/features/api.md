# API

The HTTP contract is `api/openapi.yaml` (RFC 0004). There are two implementations.

## Sub-features

- python-api: `fathom/api/` (FastAPI) served via `fathom/main.py` (`fathom-api` entrypoint / `FATHOM_PROCESS=api|jobs`) backed by `ogrl-rs` kernel, Postgres, S3, OIDC/PKCE + API token auth, and `/v1/*` + `/health`.
- mock-api: `web/src/mocks/handlers.ts` (MSW) serves the full read surface (including policies, procedures, library pin, provider bundles) plus `POST /tests/{id}/runs`, `POST /library/pull`, `POST /programs/{id}/renders`, and `POST /exports/git`, with cursor paging, filters, and `application/problem+json` errors.

## How to get to it (user POV)

Not user-facing. The web app calls `/v1/*`.

## Driving it

```bash
uv run pytest -q                                        # python API, in-memory ports, FastAPI TestClient
pnpm --dir web e2e:serve                                # then:
curl -s localhost:3200/v1/programs | jq
curl -s "localhost:3200/v1/controls?family=Resilience" | jq '.data[].id'
curl -s -XPOST localhost:3200/v1/tests/test--mfa-enforced/runs -H 'content-type: application/json' \
  -d '{"implementation_id":"nope"}' | jq                # 400 problem
```

## Gotchas

- Nothing checks the mock and the Python API against `openapi.yaml`. They can drift. Check the contract by hand when you change either.
- The Python tests use the protocol-only `StaticTokens` authenticator. Do not add real auth providers to tests.
