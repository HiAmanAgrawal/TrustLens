"""Liveness / readiness endpoints.

Kept deliberately dependency-free so a failing DB or downstream API never makes
the container appear dead to the orchestrator.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    """Return a static OK payload. No I/O — this must never fail."""
    return {"status": "ok"}
