"""Observability entrypoint (RFC 0003 section 11).

This is the sole module in OGRL that imports or configures Logfire / OpenTelemetry.
Application code logs through Python's standard `logging` module.

Runtime destination is purely configuration:
  - Unset (default): structured single-line JSON logs to stdout (CloudWatch Logs).
  - `OTEL_EXPORTER_OTLP_ENDPOINT`: exports OpenTelemetry traces/logs via OTLP.
  - `LOGFIRE_TOKEN`: sends traces/logs to hosted Logfire (when `logfire` is installed).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

log = logging.getLogger("ogrl.telemetry")

_CONFIGURED = False
_LOGFIRE_ACTIVE = False


class JsonLogFormatter(logging.Formatter):
    """Compact single-line JSON formatter suitable for CloudWatch Logs and log shippers."""

    _RESERVED = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys())

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC)
            .isoformat()
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in self._RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure(environ: Mapping[str, str] | None = None, *, force: bool = False) -> str:
    """Configure structured JSON logging and optional Logfire/OTLP instrumentation.

    Returns the active mode: `"json"`, `"otlp"`, or `"logfire"`.
    """
    global _CONFIGURED, _LOGFIRE_ACTIVE
    if _CONFIGURED and not force:
        return "logfire" if _LOGFIRE_ACTIVE else "json"

    env = os.environ if environ is None else environ
    level_name = (env.get("OGRL_LOG_LEVEL") or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLogFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    logfire_token = env.get("LOGFIRE_TOKEN") or ""
    otlp_endpoint = env.get("OTEL_EXPORTER_OTLP_ENDPOINT") or ""

    mode = "json"
    _LOGFIRE_ACTIVE = False
    if logfire_token or otlp_endpoint:
        try:
            import logfire  # type: ignore[import-not-found]

            logfire.configure(
                service_name=env.get("OTEL_SERVICE_NAME") or "ogrl",
                send_to_logfire=bool(logfire_token),
                token=logfire_token or None,
                console=False,
            )
            logfire.instrument_httpx()
            _LOGFIRE_ACTIVE = True
            mode = "logfire" if logfire_token else "otlp"
        except ImportError:
            log.warning(
                "telemetry endpoint configured but optional `logfire` package is not installed; "
                "continuing with structured JSON stdout logging"
            )

    _CONFIGURED = True
    return mode


def instrument_app(app: Any) -> None:
    """Attach FastAPI instrumentation if Logfire/OTEL was activated by `configure()`."""
    if not _LOGFIRE_ACTIVE:
        return
    try:
        import logfire  # type: ignore[import-not-found]

        logfire.instrument_fastapi(app)
    except Exception:  # pragma: no cover
        log.exception("failed to instrument FastAPI application")


def instrument_engine(engine: Any) -> None:
    """Attach SQLAlchemy instrumentation if Logfire/OTEL was activated by `configure()`."""
    if not _LOGFIRE_ACTIVE:
        return
    try:
        import logfire  # type: ignore[import-not-found]

        sync_engine = getattr(engine, "sync_engine", engine)
        logfire.instrument_sqlalchemy(engine=sync_engine)
    except Exception:  # pragma: no cover
        log.exception("failed to instrument SQLAlchemy engine")
