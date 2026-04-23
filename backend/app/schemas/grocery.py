"""Wire-level shape of the grocery analysis subsection of a verdict response.

Only ever populated when the pipeline classifies an item as ``"grocery"``;
pharma responses keep ``VerdictResponse.grocery = None`` so existing clients
see no shape change. See ``services/grocery/analyzer.py`` for what produces
these fields and ``app/schemas/status.py`` for the catalogue of codes that
``Finding.code`` may take.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.status import Severity, StatusCode

Category = Literal["pharma", "grocery", "unknown"]

OnlineFssaiStatus = Literal[
    "valid",
    "invalid",
    "expired",
    "unknown",
    "lookup_failed",
    "skipped",
]

RiskBand = Literal["low", "medium", "high", "unknown"]


class Finding(BaseModel):
    """One observation about a grocery label.

    Findings are the grocery analyser's analogue of pharma's per-field
    ``evidence`` strings — but typed, so a UI can colour-code or filter
    them. They also get mirrored into ``VerdictResponse.notes`` so the
    existing notes-timeline UI surfaces them automatically.
    """

    code: StatusCode
    severity: Severity
    message: str
    evidence: str | None = Field(
        default=None,
        description=(
            "Short snippet from the label that triggered this finding "
            "(e.g. the matched ingredient or claim phrase)."
        ),
    )


class FssaiCheck(BaseModel):
    """Result of the FSSAI license verification step.

    The format check is always performed locally and is cheap. The online
    check (foscos.fssai.gov.in) may degrade — when it does we still
    return a ``verify_url`` so the user can confirm by hand.
    """

    license_number: str | None = None
    format_valid: bool = False
    online_status: OnlineFssaiStatus = "skipped"
    business_name: str | None = None
    expiry: str | None = None
    verify_url: str = Field(
        ...,
        description="Public URL the user can open to manually verify this license.",
    )


class GroceryAnalysis(BaseModel):
    """Static-analysis report for a grocery item label."""

    risk_band: RiskBand = Field(
        ...,
        description=(
            "Coarse bucket for at-a-glance UI: ``high`` if any error-severity "
            "finding fired, ``medium`` for ≥ 2 warnings, ``low`` otherwise. "
            "``unknown`` when there was no parsable text at all."
        ),
    )
    findings: list[Finding] = Field(default_factory=list)
    dates: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Normalised dates extracted from the label, keyed by kind "
            '(e.g. ``mfg``, ``exp``, ``best_before``, ``use_by``).'
        ),
    )
    ingredients_count: int | None = Field(
        default=None,
        description=(
            "Number of distinct ingredients we could parse. ``None`` when no "
            "ingredients block was found."
        ),
    )
    fssai: FssaiCheck | None = None
