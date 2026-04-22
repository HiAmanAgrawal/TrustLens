"""Logging configuration.

A single ``configure_logging`` call wires up structured logs at app startup.
We avoid logging configuration as a module-import side effect so test runs
stay quiet unless the test explicitly opts in.
"""

from __future__ import annotations

import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    """Set the root logger to a stdout JSON-ish handler.

    TODO: swap the formatter for ``structlog`` or ``loguru`` once we decide.
    Plain ``logging`` is fine until then — premature deps add weight without
    paying for themselves.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s :: %(message)s")
    )

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
