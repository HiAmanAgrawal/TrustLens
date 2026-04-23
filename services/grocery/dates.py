"""Date extraction + freshness evaluation for grocery labels.

The pharma matcher already has solid MFG/EXP regexes — for grocery we
need two extra date kinds that aren't pharma-relevant: ``BEST BEFORE``
(quality, soft) and ``USE BY`` (safety, hard). The shared shape lets
:func:`evaluate_dates` reason about freshness without caring which keyword
produced each value.

We deliberately do *not* throw on partial dates — half the world's
packaged-snack labels write ``BB: APR 27`` (a year-relative shorthand).
``_parse`` returns ``None`` on anything we can't pin to a real day, and
the evaluator simply skips comparison rather than guessing.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Final

from app.schemas.grocery import Finding
from app.schemas.status import MESSAGES, StatusCode, _DEFAULT_SEVERITY

DateKind = str  # one of: mfg, exp, best_before, use_by

_MONTH_TOKEN: Final[str] = (
    r"(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)"
    r"[A-Z]*"
)
_MONTH_NUM: Final[dict[str, int]] = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

# Accepted shapes (case-insensitive at use site):
#   31/12/2030, 31-12-2030, 31 12 2030
#   31-DEC-2030, 31 DEC 2030, 31 DEC 30
#   DEC 2030, DEC.2030, DEC/30
_DATE_VALUE_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:"
    r"(?P<d1>\d{1,2})[\s./\-]+(?P<m1>\d{1,2}|" + _MONTH_TOKEN + r")[\s./\-]+(?P<y1>\d{2,4})"
    r"|"
    r"(?P<m2>" + _MONTH_TOKEN + r")[\s./\-]*(?P<y2>\d{2,4})"
    r"|"
    r"(?P<m3>\d{1,2})[\s./\-]+(?P<y3>\d{4})"
    r")",
    re.IGNORECASE,
)

# Keyword → date-kind. Order matters when multiple match in the same
# region of text — we keep the most-specific keyword (USE BY beats EXP).
_KEYWORDS: Final[tuple[tuple[str, DateKind], ...]] = (
    (r"use\s*by", "use_by"),
    (r"best\s*before(?:\s*end)?|bbe?", "best_before"),
    (r"exp(?:iry|ires?|\.?)?(?:\s*date|\s*dt)?", "exp"),
    (r"mfg(?:\s*date|\s*dt)?|mfd\.?(?:\s*date|\s*dt)?|"
     r"manufactur(?:ed|ing)\s*(?:on|date)?|"
     r"date\s+of\s+manufactur(?:ing|e)|packed\s*on|pkd", "mfg"),
)

# Common written-out numerals on packs that say "Best Before FOUR
# MONTHS FROM MANUFACTURE" instead of using digits. Single-word entries
# only — the rare "twenty-four month" shelf life almost always renders
# digits on real pack art, and a hyphen-aware regex would cost more
# false positives than it'd save real ones.
_NUMBER_WORDS: Final[dict[str, int]] = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "eighteen": 18, "twentyfour": 24, "thirtysix": 36,
}

# Built so the regex's alternation lists longer tokens first — otherwise
# ``one`` matches the start of ``oneself`` etc. before the longer token
# can win. Compound numbers ("twenty four") are normalised by stripping
# whitespace and hyphens before lookup, so the regex token is the
# whitespaceless form.
_NUMBER_WORD_TOKENS: Final[str] = (
    r"(?:twenty[\s\-]?four|thirty[\s\-]?six|eighteen|"
    r"twelve|eleven|ten|nine|eight|seven|six|five|four|three|two|one)"
)

# Relative shelf-life pattern: ``Best Before N months from manufacture``.
# Indian snacks frequently print this in lieu of a printed expiry date.
# We compute ``best_before = mfg + N months`` when both are present.
# ``N`` may be either digits ("4") or a word numeral ("FOUR") — Lay's,
# Britannia, Parle and other large brands all use the word form on
# bottom-of-pack stamps.
_RELATIVE_BB_RE: Final[re.Pattern[str]] = re.compile(
    r"\bbest\s*before\s+(?P<n>\d{1,2}|" + _NUMBER_WORD_TOKENS + r")\s+months?\s+"
    r"from\s+(?:date\s+of\s+)?(?:mfg|mfd|manufactur(?:e|ing))",
    re.IGNORECASE,
)


def _parse(raw: str) -> datetime | None:
    """Parse a captured date string to a UTC ``datetime`` at day-end.

    Day-end (23:59:59) so an "expires today" timestamp doesn't false-fire
    as expired during the same day. Returns ``None`` when the string
    doesn't have enough information to identify a calendar day; callers
    treat that as "unparseable, skip".
    """
    m = _DATE_VALUE_RE.search(raw)
    if not m:
        return None

    day, month, year = None, None, None
    if m.group("d1"):
        day = int(m.group("d1"))
        month = _month_to_int(m.group("m1"))
        year = int(m.group("y1"))
    elif m.group("m2"):
        month = _month_to_int(m.group("m2"))
        year = int(m.group("y2"))
        day = _last_day_of_month(month or 1, _normalise_year(year))
    elif m.group("m3"):
        month = int(m.group("m3"))
        year = int(m.group("y3"))
        day = _last_day_of_month(month, year)

    if not (day and month and year):
        return None
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    year = _normalise_year(year)
    try:
        return datetime(year, month, day, 23, 59, 59)
    except ValueError:
        return None


def _month_to_int(token: str) -> int | None:
    token = token.strip().upper()
    if token.isdigit():
        as_int = int(token)
        return as_int if 1 <= as_int <= 12 else None
    return _MONTH_NUM.get(token[:3])


def _normalise_year(year: int) -> int:
    """Two-digit years assume 2000s — packaged-food labels never refer
    to the 1900s in practice, and the alternative is silently wrong dates."""
    if year < 100:
        return 2000 + year
    return year


def _last_day_of_month(month: int, year: int) -> int:
    """Last calendar day of the given month — used when the label only
    specifies "MMM YYYY". We treat the whole month as in-date until its
    final second."""
    if month == 12:
        nxt = datetime(year + 1, 1, 1)
    else:
        nxt = datetime(year, month + 1, 1)
    return (nxt - timedelta(days=1)).day


def extract_grocery_dates(text: str) -> dict[DateKind, str]:
    """Return the most plausible date string for each kind of date keyword.

    The values are the *raw OCR snippets* (mostly so the response can
    quote them back to the user). :func:`evaluate_dates` parses them
    again on its side — keeping the two passes separate means the
    extracted dict can be displayed even if a particular value can't
    be reasoned about temporally.

    When the label says "Best Before N months from manufacture" instead
    of printing an explicit expiry, the extracted ``best_before`` snippet
    is computed as ``MFG + N months`` and stored in ``DD MMM YYYY`` form
    so :func:`evaluate_dates` can reason about it the same way as any
    explicit date.
    """
    if not text:
        return {}

    found: dict[DateKind, str] = {}
    for pattern, kind in _KEYWORDS:
        if kind in found:
            continue
        rx = re.compile(
            r"(?:" + pattern + r")"
            r"\s*[:\-\.]?\s*\n?\s*"
            r"([\dA-Za-z./\-\s]{4,30})",
            re.IGNORECASE,
        )
        # Walk every keyword occurrence and keep the first one whose
        # snippet actually contains a parseable date. Real labels often
        # say "Mfd. By: PEPSICO…" or "For manufacturing unit address…"
        # *before* they print "MFD: 22 MAR 15" further down — the old
        # ``re.search`` returned the first text match (no date) and
        # never reached the real one. We surface just the matched date
        # span (not the whole capture) so the value we hand back to the
        # user is the printed date itself, not "22 MAR 15\nMRP".
        for m in rx.finditer(text):
            snippet = m.group(1).strip(" .,-:")
            date_match = _DATE_VALUE_RE.search(snippet)
            if date_match:
                found[kind] = date_match.group(0).strip()
                break

    # Compute a synthetic best_before from "N months from manufacture"
    # when the label only states a relative shelf life. Cheap and useful
    # for snack/biscuit packs that almost never print a hard EXP date.
    if "best_before" not in found and "mfg" in found:
        rel = _RELATIVE_BB_RE.search(text)
        if rel:
            mfg_dt = _parse(found["mfg"])
            n_months = _months_from_token(rel.group("n"))
            if mfg_dt is not None and n_months is not None:
                bb_dt = _add_months(mfg_dt, n_months)
                found["best_before"] = bb_dt.strftime("%d %b %Y")

    return found


def _months_from_token(token: str) -> int | None:
    """Convert a shelf-life numeral (digit or English word) to ``int``.

    Returns ``None`` when the token isn't a recognised numeral so the
    caller can skip the synthesis without a misleading date.
    """
    if not token:
        return None
    normal = re.sub(r"[\s\-]+", "", token.strip().lower())
    if normal.isdigit():
        try:
            return int(normal)
        except ValueError:
            return None
    return _NUMBER_WORDS.get(normal)


def _add_months(base: datetime, months: int) -> datetime:
    """Add ``months`` calendar months to ``base``, clamping the day."""
    total = base.month - 1 + months
    new_year = base.year + total // 12
    new_month = total % 12 + 1
    new_day = min(base.day, _last_day_of_month(new_month, new_year))
    return base.replace(year=new_year, month=new_month, day=new_day)


def evaluate_dates(
    dates: dict[DateKind, str],
    *,
    now: datetime | None = None,
) -> list[Finding]:
    """Translate parsed dates into freshness ``Finding``s.

    Rules:
    - ``USE_BY`` or ``EXP`` already past → :data:`StatusCode.EXPIRED` (error).
    - Either expiring within 30 days → :data:`StatusCode.EXPIRES_SOON` (warning).
    - No MFG/PACKED date at all → :data:`StatusCode.MFG_DATE_MISSING` (warning).
    - MFG > 12 months ago AND EXP > 18 months from MFG → heuristic
      :data:`StatusCode.MFG_OLD_LONG_SHELF_LIFE` (info — likely preservatives).
    """
    if now is None:
        now = datetime.utcnow()

    findings: list[Finding] = []

    exp_dt = _parse(dates.get("exp", "")) if dates.get("exp") else None
    use_by_dt = _parse(dates.get("use_by", "")) if dates.get("use_by") else None
    bb_dt = _parse(dates.get("best_before", "")) if dates.get("best_before") else None
    mfg_dt = _parse(dates.get("mfg", "")) if dates.get("mfg") else None

    hard_dt = use_by_dt or exp_dt
    soft_dt = bb_dt
    primary_dt = hard_dt or soft_dt

    if primary_dt and primary_dt < now:
        findings.append(_finding(StatusCode.EXPIRED, evidence=_quote(dates, hard_dt, soft_dt)))
    elif primary_dt and (primary_dt - now) <= timedelta(days=30):
        findings.append(_finding(StatusCode.EXPIRES_SOON, evidence=_quote(dates, hard_dt, soft_dt)))

    if not mfg_dt:
        findings.append(_finding(StatusCode.MFG_DATE_MISSING))
    elif primary_dt and mfg_dt:
        manufactured_long_ago = (now - mfg_dt) > timedelta(days=365)
        long_shelf_life = (primary_dt - mfg_dt) > timedelta(days=545)  # ~18 months
        if manufactured_long_ago and long_shelf_life:
            findings.append(
                _finding(
                    StatusCode.MFG_OLD_LONG_SHELF_LIFE,
                    evidence=f"MFG {dates.get('mfg', '?')} → {dates.get('exp') or dates.get('use_by') or dates.get('best_before') or '?'}",
                )
            )

    return findings


def _quote(
    raw: dict[DateKind, str],
    hard: datetime | None,
    soft: datetime | None,
) -> str:
    """Pick the most relevant raw snippet to show the user as evidence."""
    if hard:
        return raw.get("use_by") or raw.get("exp") or ""
    if soft:
        return raw.get("best_before", "")
    return ""


def _finding(code: StatusCode, *, evidence: str | None = None) -> Finding:
    return Finding(
        code=code,
        severity=_DEFAULT_SEVERITY.get(code, "info"),
        message=MESSAGES[code],
        evidence=evidence or None,
    )
