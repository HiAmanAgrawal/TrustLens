"""
Structured JSON logging configuration for TrustLens.

WHY structured / JSON logs:
  - Supabase Logflare, Datadog, and Grafana Loki all parse JSON natively,
    so every field becomes a searchable/filterable attribute without custom
    grok patterns.
  - Agent tool calls and DB query counts attach as extra fields to the same
    log line, keeping traces coherent in low-traffic dev and high-traffic prod.

USAGE:
    from app.core.logging import get_logger
    logger = get_logger(__name__)

    logger.info("scan.completed | verdict=%s medicine_id=%s", "VERIFIED", str(id))
    logger.warning("scraper.captcha_detected | url=%s", url)
    logger.error("db.query_failed", exc_info=True)
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any


def configure_logging(log_level: str = "INFO") -> None:
    """
    Configure root logger once at app startup.

    In production (APP_ENV=production) we emit one JSON object per line.
    In development we emit human-readable output.

    Call exactly once from ``create_app()`` before any other logging.
    """
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    is_prod = os.getenv("APP_ENV", "development") == "production"

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(numeric_level)

    if is_prod:
        fmt = (
            '{"time":"%(asctime)s","level":"%(levelname)s",'
            '"logger":"%(name)s","msg":"%(message)s"}'
        )
    else:
        fmt = "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s"

    handler.setFormatter(logging.Formatter(fmt))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(numeric_level)

    # Silence noisy third-party loggers unless we are in DEBUG mode.
    if log_level.upper() != "DEBUG":
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
        logging.getLogger("playwright").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Drop-in replacement for ``logging.getLogger`` — use this everywhere."""
    return logging.getLogger(name)


def log_agent_step(
    logger: logging.Logger,
    *,
    step: str,
    tool: str | None = None,
    input_summary: str | None = None,
    output_summary: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """
    Standardised helper for logging LangGraph agent steps.

    WHY a helper: LangGraph tool calls happen inside async callbacks.
    Centralising the log format here lets us add tracing IDs or metric
    counters without editing every tool file.
    """
    parts = [f"step={step}"]
    if tool:
        parts.append(f"tool={tool}")
    if input_summary:
        parts.append(f"input={input_summary[:200]!r}")
    if output_summary:
        parts.append(f"output={output_summary[:200]!r}")
    if extra:
        parts.extend(f"{k}={v}" for k, v in extra.items())

    logger.info("agent.step | %s", "  ".join(parts))
