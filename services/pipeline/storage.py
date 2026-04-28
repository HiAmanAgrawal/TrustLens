"""
Storage condition extraction — parses OCR label text for storage instructions.

Works for both medicine and grocery labels. Indian packaged-food and pharma
labels follow a well-known vocabulary ("Store below 25°C", "Keep refrigerated",
"Store in cool dry place") so rule-based extraction is accurate enough without
an LLM and runs in microseconds.

Returned ``StorageWarning`` objects include:
  - ``condition``: machine-readable enum string (used by UI for icon selection)
  - ``message``: human-readable English instruction
  - ``severity``: "info" | "warning"  (warning for conditions that need user action)
  - ``raw_text``: the matched OCR snippet (transparency)

Multiple conditions can coexist (e.g., "keep refrigerated once opened" →
REFRIGERATE + ONCE_OPENED_REFRIGERATE).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Final

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StorageWarning:
    condition: str      # one of the _CONDITION_* constants below
    message: str        # English instruction shown to the user
    severity: str       # "info" | "warning"
    raw_text: str = ""  # matched OCR snippet for transparency


# Condition constants — stable identifiers for UI icon mapping
CONDITION_REFRIGERATE         = "refrigerate"
CONDITION_FREEZE              = "freeze"
CONDITION_COOL_DRY_PLACE      = "cool_dry_place"
CONDITION_ROOM_TEMPERATURE    = "room_temperature"
CONDITION_AVOID_SUNLIGHT      = "avoid_sunlight"
CONDITION_KEEP_DRY            = "keep_dry"
CONDITION_AWAY_FROM_CHILDREN  = "away_from_children"
CONDITION_ONCE_OPENED_USE     = "once_opened_use_within"
CONDITION_AWAY_FROM_HEAT      = "away_from_heat"
CONDITION_CONTROLLED_TEMP     = "controlled_temperature"


# ---------------------------------------------------------------------------
# Regex patterns
# Each tuple: (compiled_pattern, condition_constant, human_message, severity)
# Patterns are tried in order; all matching patterns produce a warning,
# so the list can have multiple hits (e.g., refrigerate + away_from_children).
# ---------------------------------------------------------------------------

_RULES: Final[list[tuple[re.Pattern, str, str, str]]] = [
    # ---- FREEZE (strongest, check before "refrigerate") -------------------
    (
        re.compile(
            r"\bfreeze\b|\bfrozen?\b|\bdeep[\s\-]*freeze\b|\bstore\s+(?:at|below)\s+[\-−]",
            re.IGNORECASE,
        ),
        CONDITION_FREEZE,
        "Keep frozen. Store at or below 0°C.",
        "warning",
    ),

    # ---- REFRIGERATE -------------------------------------------------------
    (
        re.compile(
            r"refrigerat(?:e|ed|or)\b|"
            r"store\s+(?:at|in|below)\s+(?:2[\s\-]?[\–\-]\s*8|between\s+2)[\s°]|"
            r"keep\s+(?:cool|cold|chilled)\b|"
            r"store\s+(?:in|at)\s+(?:a\s+)?cool\s+place\b|"
            r"(?:2|two)[\s\-]?(?:to|–|\-)\s*(?:8|eight)\s*°?[Cc]",
            re.IGNORECASE,
        ),
        CONDITION_REFRIGERATE,
        "Keep refrigerated (2–8°C). Do not freeze unless instructed.",
        "warning",
    ),

    # ---- ONCE OPENED -------------------------------------------------------
    (
        re.compile(
            r"once\s+opened[\s,]+(?:use|consume|store)\s+within\s+(\d+)\s*(days?|hours?|weeks?)|"
            r"after\s+opening[\s,]+use\s+within\s+(\d+)\s*(days?|hours?)",
            re.IGNORECASE,
        ),
        CONDITION_ONCE_OPENED_USE,
        "Once opened, use within the indicated period. Refrigerate after opening if instructed.",
        "warning",
    ),

    # ---- CONTROLLED TEMPERATURE (medicines) --------------------------------
    (
        re.compile(
            r"store\s+(?:at\s+)?(?:controlled\s+)?(?:room\s+temperature|between\s+15\s*[\-–]\s*30)|"
            r"15[\s\-]?[\–\-]\s*25\s*°?[Cc]|"
            r"25[\s\-]?°?[Cc]\s+or\s+below|"
            r"below\s+25[\s°]*[Cc]\b",
            re.IGNORECASE,
        ),
        CONDITION_CONTROLLED_TEMP,
        "Store below 25°C in a controlled environment. Avoid temperature extremes.",
        "info",
    ),

    # ---- COOL DRY PLACE ----------------------------------------------------
    (
        re.compile(
            r"cool\s+(?:and\s+)?dry\s+place|"
            r"dry\s+(?:and\s+)?cool\s+place|"
            r"store\s+in\s+a\s+(?:cool,?\s*)?dry\s+place",
            re.IGNORECASE,
        ),
        CONDITION_COOL_DRY_PLACE,
        "Store in a cool, dry place away from moisture and heat.",
        "info",
    ),

    # ---- AVOID SUNLIGHT / LIGHT -------------------------------------------
    (
        re.compile(
            r"protect(?:ed)?\s+from\s+(?:direct\s+)?(?:sun)?light|"
            r"avoid\s+(?:direct\s+)?(?:sun)?light|"
            r"store\s+away\s+from\s+(?:direct\s+)?(?:sun)?light|"
            r"keep\s+(?:out\s+of|away\s+from)\s+(?:direct\s+)?(?:sun)?light",
            re.IGNORECASE,
        ),
        CONDITION_AVOID_SUNLIGHT,
        "Protect from direct sunlight. Store in opaque or dark packaging.",
        "info",
    ),

    # ---- KEEP DRY ----------------------------------------------------------
    (
        re.compile(
            r"keep\s+dry\b|"
            r"protect\s+from\s+(?:moisture|humidity|damp)|"
            r"store\s+in\s+a\s+dry\s+place",
            re.IGNORECASE,
        ),
        CONDITION_KEEP_DRY,
        "Keep dry. Moisture may degrade the product.",
        "info",
    ),

    # ---- AWAY FROM HEAT ----------------------------------------------------
    (
        re.compile(
            r"away\s+from\s+(?:heat|direct\s+heat|flame|fire)|"
            r"keep\s+away\s+from\s+heat\b|"
            r"do\s+not\s+expose\s+to\s+(?:excessive\s+)?heat",
            re.IGNORECASE,
        ),
        CONDITION_AWAY_FROM_HEAT,
        "Keep away from heat sources and open flames.",
        "info",
    ),

    # ---- AWAY FROM CHILDREN -----------------------------------------------
    (
        re.compile(
            r"keep\s+(?:out\s+of\s+reach|away)\s+(?:of|from)\s+children|"
            r"store\s+(?:out\s+of\s+reach|away)\s+(?:of|from)\s+children",
            re.IGNORECASE,
        ),
        CONDITION_AWAY_FROM_CHILDREN,
        "Keep out of reach of children.",
        "warning",
    ),

    # ---- ROOM TEMPERATURE (catch-all for "store at room temperature") -----
    (
        re.compile(
            r"store\s+at\s+room\s+temperature|"
            r"keep\s+at\s+room\s+temperature|"
            r"room\s+temperature\b",
            re.IGNORECASE,
        ),
        CONDITION_ROOM_TEMPERATURE,
        "Store at room temperature (15–30°C).",
        "info",
    ),
]

# Conditions that are mutually exclusive with REFRIGERATE/FREEZE —
# if those are set, suppress ROOM_TEMPERATURE to avoid contradictory warnings.
_WARM_CONDITIONS = frozenset({CONDITION_ROOM_TEMPERATURE})
_COLD_CONDITIONS = frozenset({CONDITION_REFRIGERATE, CONDITION_FREEZE})


def extract_storage_warnings(text: str | None) -> list[StorageWarning]:
    """Parse OCR text and return all detected storage conditions.

    Returns an empty list if ``text`` is None/empty. Deduplicates conditions
    so the same rule can't fire twice. Resolves the REFRIGERATE vs ROOM_TEMP
    contradiction by dropping the weaker signal.
    """
    if not text or not text.strip():
        return []

    seen_conditions: set[str] = set()
    warnings: list[StorageWarning] = []

    for pattern, condition, message, severity in _RULES:
        if condition in seen_conditions:
            continue
        m = pattern.search(text)
        if m:
            raw = m.group(0).strip()
            warnings.append(StorageWarning(
                condition=condition,
                message=message,
                severity=severity,
                raw_text=raw,
            ))
            seen_conditions.add(condition)

    # Resolve contradiction: if cold storage is required, drop room-temp hint
    if seen_conditions & _COLD_CONDITIONS:
        warnings = [w for w in warnings if w.condition not in _WARM_CONDITIONS]

    return warnings
