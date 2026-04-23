"""FSSAI license extraction + verification.

Two-phase check:

1. **Local format check** — every Indian packaged-food label is required
   to print a 14-digit FSSAI license number. We extract it from the OCR
   text with a single regex, validate the format (14 digits, first digit
   1 or 2 = state code), and return that immediately. This phase is
   always cheap and always returned, even when the network phase fails.

2. **Online verification** — opens the public FSSAI FoSCoS portal in
   headless Chromium, fills in the license, and reads the result panel.
   Time-bounded; any failure (timeout, captcha, layout change, browser
   missing) degrades gracefully to ``online_status="lookup_failed"`` so
   the user can still verify by hand via the returned ``verify_url``.

The FoSCoS HTML structure changes occasionally. Treat the parsing here
as best-effort and log loudly on shape changes so we know when to update
selectors.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Final

from app.schemas.grocery import FssaiCheck

logger = logging.getLogger(__name__)

FSSAI_VERIFY_URL: Final[str] = "https://foscos.fssai.gov.in/"

# Plain 14-digit run, optionally surrounded by FSSAI keyword and an
# optional separator. Boundary uses ``\D`` so partial OCR ("12345...")
# from a longer numeric run doesn't slip in.
_LICENSE_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:fssai(?:\s*lic(?:ense|\.?)\s*(?:no\.?|number)?)?)?"
    r"\s*[:\-]?\s*"
    r"(?<!\d)(\d{14})(?!\d)",
    re.IGNORECASE,
)

# State-code prefixes for the first digit of a real FSSAI licence:
#   1 = Central / state license, 2 = state license / registration.
# Anything else is malformed.
_VALID_FIRST_DIGITS: Final[frozenset[str]] = frozenset({"1", "2"})


def extract_license(text: str) -> str | None:
    """Return the most plausible FSSAI license number, or ``None``.

    Strategy, in priority order:

    1. **Strict 14-digit** adjacent to the literal "FSSAI" / "FSSAI Lic" /
       "FSSAI Lic No" keyword. This is the canonical case and avoids
       grabbing an unrelated 14-digit run (e.g. a barcode payload
       printed elsewhere on the pack).
    2. **Bare 14-digit** anywhere in the text *if* "FSSAI" is mentioned
       at all — labels often print the keyword on one line and the
       number on the next, and OCR loses that adjacency.
    3. **Loose 12-15 digits** following any "Lic. No" / "Licence No"
       keyword. Indian packs print the FSSAI number under that label
       (often without the word "FSSAI" itself), and OCR routinely drops
       or duplicates a digit. Surfacing the captured run lets the
       caller flag :data:`StatusCode.FSSAI_FORMAT_INVALID` so the user
       sees we *found* something rather than reporting "no license at
       all". The actual number string is preserved for manual checking.
    """
    if not text:
        return None

    keyworded = re.search(
        r"fssai(?:\s*lic(?:ense|\.?)\s*(?:no\.?|number)?)?\s*[:\-]?\s*(?<!\d)(\d{14})(?!\d)",
        text,
        re.IGNORECASE,
    )
    if keyworded:
        return keyworded.group(1)

    if re.search(r"\bfssai\b", text, re.IGNORECASE):
        bare = re.search(r"(?<!\d)(\d{14})(?!\d)", text)
        if bare:
            return bare.group(1)

    # Loose path: handles OCR-mangled licenses (13 or 15 digits where
    # one digit was dropped or duplicated) printed under a "Lic. No"
    # keyword. We require a near-keyword anchor so a random 13-digit
    # number elsewhere on the pack (postal code, telephone, batch) can't
    # be mistaken for a license.
    #
    # The keyword itself is forgiven for the most common OCR substitution
    # in this font: ``c`` ↔ ``o``. Indian snack labels print "Lic. No."
    # in a small condensed face that Tesseract routinely misreads as
    # "Lio,". Punctuation between the keyword and the digits is allowed
    # to drift — commas, periods, and colons are interchangeable noise
    # at the OCR level.
    loose = re.search(
        r"\bli[co](?:en[cs]e)?[.,]?\s*(?:no\.?|number)?[.,]?\s*[:\-]?\s*"
        r"(?<!\d)(\d{12,15})(?!\d)",
        text,
        re.IGNORECASE,
    )
    if loose:
        return loose.group(1)

    return None


def validate_format(license_number: str | None) -> bool:
    """True iff ``license_number`` is exactly 14 digits, leading 1 or 2."""
    if not license_number or len(license_number) != 14 or not license_number.isdigit():
        return False
    return license_number[0] in _VALID_FIRST_DIGITS


async def verify_online(
    license_number: str,
    *,
    timeout_s: float = 10.0,
) -> FssaiCheck:
    """Look up ``license_number`` on the FoSCoS portal.

    Always returns a ``FssaiCheck``. Network / browser / parse failures
    set ``online_status="lookup_failed"`` and keep ``verify_url``
    populated so the user can confirm by hand.

    Reuses the Playwright singleton from :mod:`services.scraper.agent`
    so we don't pay the ~1–2 s Chromium startup more than once per
    process lifetime.
    """
    base = FssaiCheck(
        license_number=license_number,
        format_valid=validate_format(license_number),
        online_status="lookup_failed",
        verify_url=FSSAI_VERIFY_URL,
    )

    if not validate_format(license_number):
        return base

    try:
        from services.scraper.agent import _get_browser  # type: ignore[attr-defined]
    except ImportError:
        logger.warning("Playwright unavailable; FSSAI online check skipped.")
        return base

    try:
        browser = await _get_browser()
    except Exception as exc:
        logger.warning("Couldn't launch headless browser for FSSAI check: %s", exc)
        return base

    context = await browser.new_context()
    page = await context.new_page()
    try:
        try:
            await page.goto(
                FSSAI_VERIFY_URL,
                wait_until="domcontentloaded",
                timeout=int(timeout_s * 1000),
            )
        except Exception as exc:
            logger.warning("FSSAI page load failed: %s", exc)
            return base

        # FoSCoS exposes a license-search input on its landing page.
        # Selector list is intentionally generous — the portal occasionally
        # renames its inputs but keeps the visible behaviour the same.
        selectors = (
            "input[name='licenseNo']",
            "input[name='licenceNo']",
            "input[id='licenseNo']",
            "input[placeholder*='License']",
            "input[placeholder*='Licence']",
        )
        target = None
        for sel in selectors:
            handle = await page.query_selector(sel)
            if handle:
                target = handle
                break
        if target is None:
            logger.warning("FSSAI page layout changed: no licence input found.")
            return base

        try:
            await target.fill(license_number)
            await page.keyboard.press("Enter")
            await page.wait_for_load_state("networkidle", timeout=int(timeout_s * 1000))
        except Exception as exc:
            logger.warning("FSSAI submission failed: %s", exc)
            return base

        body = (await page.content()).lower()
        return _parse_result(body, license_number)
    finally:
        await context.close()


def _parse_result(html_lower: str, license_number: str) -> FssaiCheck:
    """Best-effort scrape of the FoSCoS result panel.

    The portal returns either a small "no record found" string or a
    table with company name, business type, and validity. We do *not*
    attempt to parse the full table — only the signals we need to
    decide ``online_status``.
    """
    base = FssaiCheck(
        license_number=license_number,
        format_valid=validate_format(license_number),
        online_status="lookup_failed",
        verify_url=FSSAI_VERIFY_URL,
    )

    if any(token in html_lower for token in (
        "no record found",
        "no records found",
        "invalid license",
        "invalid licence",
    )):
        return base.model_copy(update={"online_status": "invalid"})

    expired = ("expired" in html_lower) or ("license expired" in html_lower)
    valid = ("valid" in html_lower) or ("active" in html_lower)

    if expired and not valid:
        return base.model_copy(update={"online_status": "expired"})

    if valid:
        return base.model_copy(
            update={
                "online_status": "valid",
                "business_name": _extract_label(html_lower, "company name") or _extract_label(html_lower, "name of company"),
                "expiry": _extract_label(html_lower, "valid up to") or _extract_label(html_lower, "validity"),
            }
        )

    return base.model_copy(update={"online_status": "unknown"})


def _extract_label(html_lower: str, label: str) -> str | None:
    """Pluck a value next to a ``<…>label</…> <…>value</…>`` cell pair.

    Crude — we just grep for "label … 1–80 chars". Good enough to surface
    something to the user; the trustworthy state is ``online_status``,
    not these helper fields.
    """
    m = re.search(rf"{re.escape(label)}\s*[:\s<>/a-z\"']{{0,40}}([a-z0-9 .,\-/]{{2,80}})", html_lower)
    if not m:
        return None
    val = m.group(1).strip(" .,:-")
    return val.title() if val else None


def is_expired(check: FssaiCheck, *, now: datetime | None = None) -> bool:
    """Convenience: best-effort parse of ``check.expiry`` against ``now``."""
    if not check.expiry:
        return False
    if now is None:
        now = datetime.utcnow()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(check.expiry, fmt) < now
        except ValueError:
            continue
    return False
