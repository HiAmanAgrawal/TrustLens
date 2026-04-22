"""Smoke test: the app boots and `/health` answers.

Kept in the scaffold so a fresh clone can run ``pytest`` and immediately know
whether the import graph is intact.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_health_ok() -> None:
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
