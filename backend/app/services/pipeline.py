"""HTTP-facing glue: turn an image (or a typed code) into a ``VerdictResponse``.

Both ``routes_images`` and ``routes_codes`` go through here so the orchestration
lives in one place. Anything that touches more than one ``services/*`` package
or maps domain objects to the wire schema belongs in this module.

Each stage produces a small, framework-free status string. We translate those
into ``StatusCode`` notes here — the services stay HTTP-agnostic and the
response gains a single, consistent way to communicate what happened.
"""

from __future__ import annotations

import asyncio
import logging

from app.schemas.grocery import Category, GroceryAnalysis
from app.schemas.status import MESSAGES, Note, StatusCode, make_note
from app.schemas.verdict import BarcodeInfo, OcrInfo, PageInfo, VerdictResponse
from services import classifier
from services.barcode import decoder as barcode_decoder
from services.grocery import analyzer as grocery_analyzer
from services.matcher import engine as matcher_engine
from services.matcher.engine import Verdict
from services.ocr import extractor as ocr_extractor
from services.ocr.extractor import OcrResult
from services.scraper import agent as scraper_agent
from services.scraper.agent import ScrapeResult

logger = logging.getLogger(__name__)

# Hard wall-clock for a manufacturer-portal scrape. Past this we'd rather
# return an "unverifiable" verdict than make the user wait.
_SCRAPE_TIMEOUT_S = 20.0


async def verify_image(image_bytes: bytes) -> VerdictResponse:
    """Image input path: decode barcode + OCR in parallel, then route by category.

    Two branches share the same response shape:

    - **pharma / unknown**: scrape the manufacturer portal (when the QR is a
      URL) and run the rule-based label-vs-page matcher.
    - **grocery**: skip the portal scrape — there is none — and run the
      static grocery analyser (dates, ingredients, nutrition, claims, FSSAI).

    The classifier defaults to ``"pharma"``-leaning for ambiguous text, so
    existing pharma traffic keeps the same behaviour. ``"unknown"`` items
    still go through the matcher (best-effort) so we never silently skip
    work on a real label.
    """
    logger.info("Pipeline: starting verify_image (%d bytes)", len(image_bytes))

    barcode, ocr = await asyncio.gather(
        # Decoders are sync C-bound work; offload so we don't stall the loop.
        asyncio.to_thread(barcode_decoder.decode, image_bytes),
        ocr_extractor.extract_text(image_bytes),
    )

    logger.info("Pipeline: barcode=%s, ocr_engine=%s, ocr_status=%s, ocr_chars=%d",
                barcode.status if barcode else "none",
                ocr.engine, ocr.status, len(ocr.text))

    # Only feed the scraper a payload we actually decoded. A
    # 'detected_undecoded' result means the QR exists but its data is unreadable —
    # we surface that in the response so the user knows to retake the photo, but
    # it isn't a usable URL.
    decoded_payload = barcode.payload if (barcode and barcode.is_decoded) else None

    category = classifier.classify(
        barcode_payload=decoded_payload,
        barcode_symbology=barcode.symbology if barcode else None,
        ocr_text=ocr.text if ocr else None,
    )

    if category == "grocery":
        grocery_result = await grocery_analyzer.analyze(ocr.text or "")
        verdict = _verdict_from_grocery(grocery_result, ocr_text=ocr.text)
        return _to_response(
            verdict,
            barcode=barcode,
            ocr=ocr,
            page=None,
            category=category,
            grocery=grocery_result,
        )

    page = await _maybe_scrape(decoded_payload)

    logger.info("Pipeline: scrape=%s, page_fields=%d",
                page.status if page else "skipped",
                len(page.fields) if page and page.fields else 0)

    verdict = await matcher_engine.match(
        barcode_payload=decoded_payload,
        ocr_text=ocr.text if ocr.text else None,
        scrape_data=page.fields if page and page.status == "ok" else None,
    )

    logger.info("Pipeline: verdict=%s, score=%d, label_fields=%s, page_fields=%s",
                verdict.verdict, verdict.score,
                list(verdict.label_fields.keys()),
                list(verdict.page_fields.keys()))

    return _to_response(verdict, barcode=barcode, ocr=ocr, page=page)


async def verify_code(code: str) -> VerdictResponse:
    """Code-text path: skip image decoding entirely.

    The user has already provided the decoded string (typed off a pack, copied
    from an invoice, ...). If it's a URL we still scrape — that's the only
    side we have to compare against here, so a verdict will land at
    "unverifiable" without it.

    No grocery analysis on this path: there's no OCR'd label to inspect,
    so we always treat the request as pharma.
    """
    page = await _maybe_scrape(code)
    verdict = await matcher_engine.match(
        barcode_payload=code,
        ocr_text=None,
        scrape_data=page.fields if page and page.status == "ok" else None,
    )
    # No real BarcodeResult on this path; synthesise a minimal one so the
    # response still tells the client what we used.
    barcode = barcode_decoder.BarcodeResult(
        payload=code, symbology="USER_INPUT", rotation=0, status="decoded"
    )
    return _to_response(verdict, barcode=barcode, ocr=None, page=page, category="pharma")


async def _maybe_scrape(payload: str | None) -> ScrapeResult | None:
    """Scrape when the payload looks like a URL; otherwise skip cleanly.

    Returns ``None`` only when there is no URL to follow. All other outcomes
    (including failures) come back as a ``ScrapeResult`` with a non-"ok"
    ``status`` so the response can explain what went wrong.
    """
    if not payload:
        return None
    if not payload.lower().startswith(("http://", "https://")):
        return None
    try:
        return await asyncio.wait_for(
            scraper_agent.scrape_url(payload, timeout_s=_SCRAPE_TIMEOUT_S),
            timeout=_SCRAPE_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        logger.warning("Scrape of %s timed out after %.1fs", payload, _SCRAPE_TIMEOUT_S)
        return ScrapeResult(url=payload, status="timeout", error_detail="wall-clock timeout")
    except Exception as exc:
        logger.exception("Scrape of %s failed.", payload)
        return ScrapeResult(url=payload, status="failed", error_detail=str(exc)[:200])


# ---- Response assembly ------------------------------------------------------


# Maps the free-form status strings each service emits onto the canonical
# StatusCode enum. Keeping the mapping in one place means a service can rename
# its internal labels without rippling through every layer.
_OCR_STATUS_TO_CODE: dict[str, StatusCode] = {
    "ok": StatusCode.OCR_OK,
    "low_confidence": StatusCode.OCR_LOW_CONFIDENCE,
    "no_text": StatusCode.OCR_NO_TEXT,
    "tesseract_missing": StatusCode.OCR_TESSERACT_MISSING,
    "fallback_used": StatusCode.OCR_FALLBACK_USED,
    "fallback_unavailable": StatusCode.OCR_FALLBACK_UNAVAILABLE,
    "fallback_auth_failed": StatusCode.OCR_FALLBACK_AUTH_FAILED,
    "fallback_rate_limited": StatusCode.OCR_FALLBACK_RATE_LIMITED,
    "fallback_failed": StatusCode.OCR_FALLBACK_FAILED,
    "image_unreadable": StatusCode.IMAGE_UNREADABLE,
}

_SCRAPE_STATUS_TO_CODE: dict[str, StatusCode] = {
    "ok": StatusCode.SCRAPE_OK,
    "timeout": StatusCode.SCRAPE_TIMEOUT,
    "dns_failed": StatusCode.SCRAPE_DNS_FAILED,
    "http_error": StatusCode.SCRAPE_HTTP_ERROR,
    "captcha_blocked": StatusCode.SCRAPE_CAPTCHA_BLOCKED,
    "browser_unavailable": StatusCode.SCRAPE_BROWSER_UNAVAILABLE,
    "failed": StatusCode.SCRAPE_FAILED,
}

_VERDICT_TO_CODE: dict[str, StatusCode] = {
    "safe": StatusCode.MATCH_OK,
    "caution": StatusCode.MATCH_PARTIAL,
    "high_risk": StatusCode.MATCH_DISAGREES,
    "unverifiable": StatusCode.MATCH_UNVERIFIABLE,
}

# Routing -> Note. These are info-level and just tell the client which
# branch ran, so they don't dominate severity-based status picking.
_CATEGORY_TO_CODE: dict[Category, StatusCode] = {
    "pharma": StatusCode.CATEGORY_PHARMA,
    "grocery": StatusCode.CATEGORY_GROCERY,
    "unknown": StatusCode.CATEGORY_UNKNOWN,
}

# Grocery risk-band -> matcher verdict label. We reuse the matcher's
# verdict shape so /images responses stay polymorphic-but-consistent;
# the per-finding detail lives in ``VerdictResponse.grocery``.
_RISK_TO_VERDICT: dict[str, str] = {
    "high": "high_risk",
    "medium": "caution",
    "low": "safe",
    "unknown": "unverifiable",
}

# Score buckets for grocery — same 0-10 scale as pharma so the UI's
# numeric display works without branching.
_RISK_TO_SCORE: dict[str, int] = {
    "high": 2,
    "medium": 5,
    "low": 9,
    "unknown": 0,
}


def _verdict_from_grocery(grocery: GroceryAnalysis, *, ocr_text: str | None) -> Verdict:
    """Synthesise a :class:`Verdict` from a :class:`GroceryAnalysis`.

    The grocery analyser produces structured findings; the existing
    response shape expects a ``Verdict`` with ``score``, ``verdict``,
    ``summary``, and ``evidence``. Mapping is intentionally simple so
    the two branches feel consistent in the UI:

    - ``risk_band`` collapses onto the matcher's verdict labels
      (``high → high_risk``, etc.).
    - Score buckets pick a representative midpoint of each band.
    - Evidence is the per-finding ``"message — quoted_evidence"`` strings
      so the same UI element that renders pharma evidence renders these.
    """
    verdict_label = _RISK_TO_VERDICT.get(grocery.risk_band, "unverifiable")
    score = _RISK_TO_SCORE.get(grocery.risk_band, 0)
    summary = _GROCERY_SUMMARIES.get(grocery.risk_band, "Grocery analysis completed.")

    evidence: list[str] = []
    for finding in grocery.findings:
        if finding.evidence:
            evidence.append(f"{finding.message} ({finding.evidence})")
        else:
            evidence.append(finding.message)

    return Verdict(
        score=score,
        verdict=verdict_label,  # type: ignore[arg-type]
        summary=summary,
        evidence=evidence,
        barcode_payload=None,
        label_text=ocr_text,
        page_text=None,
        label_fields={},
        page_fields={},
    )


_GROCERY_SUMMARIES: dict[str, str] = {
    "high": "We found one or more serious issues with this grocery label.",
    "medium": "We found a few things on this grocery label worth a closer look.",
    "low": "Nothing concerning stood out on this grocery label.",
    "unknown": "We couldn't read enough of the label to analyse it.",
}


def _collect_notes(
    *,
    barcode: barcode_decoder.BarcodeResult | None,
    ocr: OcrResult | None,
    page: ScrapeResult | None,
    verdict: Verdict,
    user_supplied_code: bool,
    category: Category,
    grocery: GroceryAnalysis | None,
) -> list[Note]:
    """Build the ordered list of notes that explains what the pipeline did."""
    notes: list[Note] = []

    # --- Barcode --------------------------------------------------------
    if not user_supplied_code:
        if barcode is None:
            notes.append(make_note(StatusCode.QR_NOT_FOUND))
        elif barcode.status == "detected_undecoded":
            notes.append(make_note(StatusCode.QR_DETECTED_UNREADABLE))
        elif barcode.is_decoded and not _looks_like_url(barcode.payload):
            notes.append(make_note(StatusCode.QR_NOT_A_URL))

    # --- OCR ------------------------------------------------------------
    if ocr is not None:
        ocr_code = _OCR_STATUS_TO_CODE.get(ocr.status, StatusCode.OCR_OK)
        notes.append(make_note(ocr_code))

    # --- Routing --------------------------------------------------------
    # Append the category note before any branch-specific notes so the UI
    # sees "we treated this as X" alongside the per-stage outcomes.
    notes.append(make_note(_CATEGORY_TO_CODE[category]))

    if category == "grocery" and grocery is not None:
        # Grocery branch: there is no scrape; the verdict comes from
        # static analysis. Surface every finding as a Note so the existing
        # notes-timeline UI shows the full breakdown without needing to
        # learn the new ``grocery`` field.
        for finding in grocery.findings:
            notes.append(
                Note(
                    code=finding.code,
                    message=finding.message,
                    severity=finding.severity,
                )
            )
        return notes

    # --- Scraper --------------------------------------------------------
    if page is None:
        # Only worth mentioning on the image path (the code path always
        # produces a page or skips with a code-specific reason already noted).
        if not user_supplied_code and barcode is not None and barcode.is_decoded:
            # Decoded but not a URL — already noted above as QR_NOT_A_URL.
            pass
        elif user_supplied_code:
            notes.append(make_note(StatusCode.SCRAPE_SKIPPED))
    else:
        scrape_code = _SCRAPE_STATUS_TO_CODE.get(page.status, StatusCode.SCRAPE_FAILED)
        if scrape_code is StatusCode.SCRAPE_HTTP_ERROR and page.http_status:
            notes.append(
                Note(
                    code=scrape_code,
                    message=f"{MESSAGES[scrape_code]} (HTTP {page.http_status})",
                    severity="warning",
                )
            )
        else:
            notes.append(make_note(scrape_code))

    # --- Matcher --------------------------------------------------------
    # Special case: on the /codes path with no OCR but a populated page —
    # we have only one side, so the matcher rightly returns "unverifiable",
    # but the user is better served by an "info only" framing. They didn't
    # *ask* us to compare; they asked "what does this QR point to?".
    is_info_only = (
        user_supplied_code
        and ocr is None
        and page is not None
        and page.status == "ok"
        and bool(verdict.page_fields)
    )
    if is_info_only:
        notes.append(make_note(StatusCode.INFO_ONLY))
    else:
        notes.append(make_note(_VERDICT_TO_CODE[verdict.verdict]))

    return notes


def _pick_top_status(notes: list[Note], verdict: Verdict) -> tuple[StatusCode, str]:
    """Choose the single status + message we'll surface at the top level.

    Priority: the most actionable note wins. Errors beat warnings beat info,
    and within a tier we prefer notes from earlier pipeline stages because
    that's usually where the user can intervene (retake a photo > tweak a
    URL > complain about a 5xx).

    Category notes (``CATEGORY_PHARMA`` etc.) are routing-only and never
    actionable by themselves, so they're filtered out of the top-status
    selection — they still appear in the notes timeline.
    """
    severity_rank = {"error": 0, "warning": 1, "info": 2}
    actionable = [
        n for n in notes
        if n.code not in (
            StatusCode.OCR_OK,
            StatusCode.SCRAPE_OK,
            StatusCode.MATCH_OK,
            StatusCode.CATEGORY_PHARMA,
            StatusCode.CATEGORY_GROCERY,
            StatusCode.CATEGORY_UNKNOWN,
        )
    ]
    if actionable:
        actionable.sort(key=lambda n: severity_rank.get(n.severity, 3))
        top = actionable[0]
        return top.code, top.message

    # Everything succeeded — surface the verdict's own message.
    code = _VERDICT_TO_CODE[verdict.verdict]
    return code, MESSAGES[code]


def _looks_like_url(s: str) -> bool:
    return s.lower().startswith(("http://", "https://"))


def _to_response(
    verdict: Verdict,
    *,
    barcode: barcode_decoder.BarcodeResult | None,
    ocr: OcrResult | None,
    page: ScrapeResult | None,
    category: Category = "pharma",
    grocery: GroceryAnalysis | None = None,
) -> VerdictResponse:
    """Adapt domain objects to the public Pydantic schema."""
    user_supplied_code = barcode is not None and barcode.symbology == "USER_INPUT"

    notes = _collect_notes(
        barcode=barcode,
        ocr=ocr,
        page=page,
        verdict=verdict,
        user_supplied_code=user_supplied_code,
        category=category,
        grocery=grocery,
    )
    top_status, top_message = _pick_top_status(notes, verdict)

    page_info = None
    if page is not None and page.fields:
        page_info = PageInfo(
            url=page.url,
            title=page.fields.get("title"),
            text=page.fields.get("visible_text"),
            captcha_detected=page.status == "captcha_blocked",
        )

    return VerdictResponse(
        status=top_status,
        message=top_message,
        notes=notes,
        verdict=verdict.verdict,
        score=verdict.score,
        summary=verdict.summary,
        evidence=verdict.evidence,
        barcode=BarcodeInfo(
            payload=barcode.payload,
            symbology=barcode.symbology,
            rotation=barcode.rotation,
            status=barcode.status,
        )
        if barcode
        else None,
        ocr=OcrInfo(engine=ocr.engine, confidence=ocr.confidence, text=ocr.text) if ocr else None,
        page=page_info,
        label_fields=verdict.label_fields,
        page_fields=verdict.page_fields,
        category=category,
        grocery=grocery,
    )
