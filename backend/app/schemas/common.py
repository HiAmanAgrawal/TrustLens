"""
Shared Pydantic building blocks used across every domain schema.

``TrustLensResponse`` wraps every API response so clients can reliably check
``ok`` and branch on ``data`` vs ``error`` without inspecting HTTP codes.
"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

DataT = TypeVar("DataT")


class TrustLensResponse(BaseModel, Generic[DataT]):
    """
    Standard API response envelope.

    Every endpoint returns this wrapper so frontend clients have a single
    contract regardless of the resource type.

    Example:
        {"ok": true, "data": {...}, "error": null}
        {"ok": false, "data": null, "error": "Medicine not found."}
    """

    ok: bool
    data: DataT | None = None
    error: str | None = None

    @classmethod
    def success(cls, data: DataT) -> "TrustLensResponse[DataT]":
        return cls(ok=True, data=data)

    @classmethod
    def failure(cls, message: str) -> "TrustLensResponse[None]":
        return cls(ok=False, error=message)


class PaginatedResponse(BaseModel, Generic[DataT]):
    """Pagination wrapper for list endpoints."""

    items: list[DataT]
    total: int
    page: int
    page_size: int
    has_next: bool

    model_config = ConfigDict(from_attributes=True)
