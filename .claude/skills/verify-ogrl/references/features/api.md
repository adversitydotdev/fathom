# API

The HTTP contract is `api/openapi.yaml` (RFC 0004). There are two implementations.

## Sub-features

- python-api: `ogrl/api/` (FastAPI). It is built with `create_app(container)` and has no standalone server entrypoint yet. Implemented paths: meta and controls.
- mock-api: `web/src/mocks/handlers.ts` (MSW) serves the full read surface plus `POST /tests/{id}/runs`, with cursor paging, filters, and `application/problem+json` errors.

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
