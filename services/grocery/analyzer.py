"""Top-level grocery analyser.

Orchestrates the per-aspect modules (dates, ingredients, nutrition,
claims, FSSAI) and turns their findings into a single
:class:`GroceryAnalysis`. The pipeline calls :func:`analyze` once per
``/images`` request that classifies as grocery; nothing in here touches
HTTP, so it stays unit-testable in isolation.

Risk band rules (kept simple by design — easier to reason about than a
weighted score):

- Any ``error``-severity finding         → ``"high"``.
- Two or more ``warning``-severity       → ``"medium"``.
- Otherwise (only info, or no findings)  → ``"low"``.
- Empty / unparseable text               → ``"unknown"``.
"""

from __future__ import annotations

import logging
from datetime import datetime

from app.schemas.grocery import FssaiCheck, Finding, GroceryAnalysis, RiskBand
from app.schemas.status import MESSAGES, StatusCode, _DEFAULT_SEVERITY

from .claims import find_vague_claims
from .dates import evaluate_dates, extract_grocery_dates
from .fssai import (
    FSSAI_VERIFY_URL,
    extract_license,
    is_expired,
    validate_format,
    verify_online,
)
from .ingredients import analyze_ingredients, extract_ingredients_block
from .nutrition import evaluate_nutrition, parse_nutrition

logger = logging.getLogger(__name__)


async def analyze(
    ocr_text: str | None,
    *,
    now: datetime | None = None,
    online_fssai: bool = True,
) -> GroceryAnalysis:
    """Run the full grocery static-analysis pass.

    Args:
        ocr_text: The raw OCR transcription of the label. ``None`` /
            empty triggers a ``risk_band="unknown"`` shortcut.
        now: Override "current time" for date evaluation. Tests use this
            to keep fixtures deterministic.
        online_fssai: When ``False``, skips the FoSCoS lookup and uses
            local format validation only. Useful for tests and rate-limited
            environments.

    Returns:
        A populated :class:`GroceryAnalysis`.
    """
    if not ocr_text or not ocr_text.strip():
        return GroceryAnalysis(risk_band="unknown", findings=[], dates={}, ingredients_count=None, fssai=None)

    findings: list[Finding] = []

    dates = extract_grocery_dates(ocr_text)
    findings += evaluate_dates(dates, now=now)

    block = extract_ingredients_block(ocr_text)
    ing_findings, ingredients_count = analyze_ingredients(block)
    findings += ing_findings

    nutrition = parse_nutrition(ocr_text)
    if nutrition is None:
        findings.append(_finding(StatusCode.NUTRITION_TABLE_MISSING))
    else:
        findings += evaluate_nutrition(nutrition)

    findings += find_vague_claims(ocr_text, ingredients_block=block)

    fssai = await _check_fssai(ocr_text, online=online_fssai)
    findings += _fssai_findings(fssai)

    return GroceryAnalysis(
        risk_band=_risk_band(findings),
        findings=findings,
        dates=dates,
        ingredients_count=ingredients_count,
        fssai=fssai,
    )


async def _check_fssai(ocr_text: str, *, online: bool) -> FssaiCheck:
    """Run the FSSAI extract → format → online pipeline, returning a check."""
    license_number = extract_license(ocr_text)
    if not license_number:
        return FssaiCheck(
            license_number=None,
            format_valid=False,
            online_status="skipped",
            verify_url=FSSAI_VERIFY_URL,
        )

    if not validate_format(license_number):
        return FssaiCheck(
            license_number=license_number,
            format_valid=False,
            online_status="skipped",
            verify_url=FSSAI_VERIFY_URL,
        )

    if not online:
        return FssaiCheck(
            license_number=license_number,
            format_valid=True,
            online_status="skipped",
            verify_url=FSSAI_VERIFY_URL,
        )

    try:
        return await verify_online(license_number)
    except Exception as exc:
        # Last-line defence: never let an FSSAI lookup blow up the whole
        # response. Log loudly and return the local-only result.
        logger.exception("FSSAI online verification crashed: %s", exc)
        return FssaiCheck(
            license_number=license_number,
            format_valid=True,
            online_status="lookup_failed",
            verify_url=FSSAI_VERIFY_URL,
        )


def _fssai_findings(check: FssaiCheck) -> list[Finding]:
    """Translate an :class:`FssaiCheck` into ``Finding``s for the timeline."""
    findings: list[Finding] = []
    if check.license_number is None:
        findings.append(_finding(StatusCode.FSSAI_NOT_FOUND_ON_LABEL))
        return findings

    if not check.format_valid:
        findings.append(_finding(StatusCode.FSSAI_FORMAT_INVALID, evidence=check.license_number))
        return findings

    if check.online_status == "valid":
        findings.append(_finding(StatusCode.FSSAI_VALID, evidence=check.license_number))
        if is_expired(check):
            findings.append(_finding(StatusCode.FSSAI_LICENSE_EXPIRED, evidence=check.expiry))
        return findings

    if check.online_status == "expired":
        findings.append(_finding(StatusCode.FSSAI_LICENSE_EXPIRED, evidence=check.license_number))
        return findings

    if check.online_status == "invalid":
        findings.append(_finding(StatusCode.FSSAI_FORMAT_INVALID, evidence=check.license_number))
        return findings

    if check.online_status in ("lookup_failed", "skipped", "unknown"):
        findings.append(_finding(StatusCode.FSSAI_VALID, evidence=check.license_number))
        if check.online_status == "lookup_failed":
            findings.append(_finding(StatusCode.FSSAI_LOOKUP_FAILED))
    return findings


def _risk_band(findings: list[Finding]) -> RiskBand:
    """Bucketise ``findings`` into a coarse risk band."""
    if not findings:
        return "low"
    severities = [f.severity for f in findings]
    if "error" in severities:
        return "high"
    if severities.count("warning") >= 2:
        return "medium"
    return "low"


def _finding(code: StatusCode, *, evidence: str | None = None) -> Finding:
    return Finding(
        code=code,
        severity=_DEFAULT_SEVERITY.get(code, "info"),
        message=MESSAGES[code],
        evidence=evidence or None,
    )
