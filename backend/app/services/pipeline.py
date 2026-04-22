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

from app.schemas.status import MESSAGES, Note, StatusCode, make_note
from app.schemas.verdict import BarcodeInfo, OcrInfo, PageInfo, VerdictResponse
from services.barcode import decoder as barcode_decoder
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
    """Image input path: decode barcode + OCR in parallel, scrape if URL, match."""
    barcode, ocr = await asyncio.gather(
        # Decoders are sync C-bound work; offload so we don't stall the loop.
        asyncio.to_thread(barcode_decoder.decode, image_bytes),
        ocr_extractor.extract_text(image_bytes),
    )
    # Only feed the scraper a payload we actually decoded. A
    # 'detected_undecoded' result means the QR exists but its data is unreadable —
    # we surface that in the response so the user knows to retake the photo, but
    # it isn't a usable URL.
    decoded_payload = barcode.payload if (barcode and barcode.is_decoded) else None
    page = await _maybe_scrape(decoded_payload)
    verdict = await matcher_engine.match(
        barcode_payload=decoded_payload,
        ocr_text=ocr.text if ocr.text else None,
        scrape_data=page.fields if page and page.status == "ok" else None,
    )
    return _to_response(verdict, barcode=barcode, ocr=ocr, page=page)


async def verify_code(code: str) -> VerdictResponse:
    """Code-text path: skip image decoding entirely.

    The user has already provided the decoded string (typed off a pack, copied
    from an invoice, ...). If it's a URL we still scrape — that's the only
    side we have to compare against here, so a verdict will land at
    "unverifiable" without it.
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
    return _to_response(verdict, barcode=barcode, ocr=None, page=page)


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


def _collect_notes(
    *,
    barcode: barcode_decoder.BarcodeResult | None,
    ocr: OcrResult | None,
    page: ScrapeResult | None,
    verdict: Verdict,
    user_supplied_code: bool,
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
    """
    severity_rank = {"error": 0, "warning": 1, "info": 2}
    actionable = [
        n for n in notes
        if n.code not in (StatusCode.OCR_OK, StatusCode.SCRAPE_OK, StatusCode.MATCH_OK)
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
) -> VerdictResponse:
    """Adapt domain objects to the public Pydantic schema."""
    user_supplied_code = barcode is not None and barcode.symbology == "USER_INPUT"

    notes = _collect_notes(
        barcode=barcode,
        ocr=ocr,
        page=page,
        verdict=verdict,
        user_supplied_code=user_supplied_code,
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
    )
