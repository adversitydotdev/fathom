# Multi-stage production image for `ogrl` (API + job worker; RFC 0003 §2 & §9).
# Uses the prebuilt `ogrl-rs` manylinux wheel from `uv.lock` — no Rust compiler needed.

FROM ghcr.io/astral-sh/uv:0.7-python3.13-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --no-dev

COPY ogrl ./ogrl
COPY api ./api
COPY alembic.ini ./
RUN uv sync --frozen --no-dev


FROM python:3.13-slim-bookworm AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system ogrl \
    && useradd --system --gid ogrl --create-home ogrl \
    && groupadd --system ogrl-harness \
    && useradd --system --gid ogrl-harness --no-create-home ogrl-harness

WORKDIR /app
COPY --from=builder --chown=ogrl:ogrl /app/.venv /app/.venv
COPY --from=builder --chown=ogrl:ogrl /app/ogrl /app/ogrl
COPY --from=builder --chown=ogrl:ogrl /app/api /app/api
COPY --from=builder --chown=ogrl:ogrl /app/alembic.ini /app/alembic.ini

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYDANTIC_AI_NO_BANNER=1 \
    OGRL_BIND="0.0.0.0:8080"

USER ogrl
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)"

CMD ["ogrl"]
