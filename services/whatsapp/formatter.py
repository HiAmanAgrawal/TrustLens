"""Format ``VerdictResponse`` into WhatsApp-friendly plain text.

WhatsApp supports a small subset of formatting:
- *bold*  (single asterisks)
- _italic_ (single underscores)
- ~strikethrough~ (single tildes)
- ```monospace``` (triple backticks)

We stick to *bold* and plain text so messages render cleanly on all devices.
"""

from __future__ import annotations

from typing import Any


# Emoji mapping for verdicts.
_VERDICT_EMOJI = {
    "safe": "GREEN",
    "caution": "YELLOW",
    "high_risk": "RED",
    "unverifiable": "GREY",
}

_VERDICT_ICON = {
    "safe": "SAFE",
    "caution": "CAUTION",
    "high_risk": "HIGH RISK",
    "unverifiable": "UNVERIFIABLE",
}


_DISCLAIMER = (
    "_Disclaimer: TrustLens is an AI-powered tool. "
    "This is not a substitute for professional medical advice. "
    "Consult a pharmacist or doctor if in doubt._"
)

_FIELD_LABELS = {
    "drug_name": "Drug",
    "batch": "Batch",
    "mfg_date": "Mfg Date",
    "exp_date": "Exp Date",
    "manufacturer": "Manufacturer",
    "brand_name": "Brand",
    "mrp": "MRP",
    "composition": "Composition",
}


def _format_fields(label_fields: dict, page_fields: dict) -> list[str]:
    """Format extracted fields into display lines."""
    lines: list[str] = []
    all_fields = {**label_fields, **page_fields}
    if not all_fields:
        return lines
    for key, label in _FIELD_LABELS.items():
        val = label_fields.get(key) or page_fields.get(key)
        if val:
            lines.append(f"  *{label}:* {val}")
    shown = set(_FIELD_LABELS.keys())
    for key, val in all_fields.items():
        if key not in shown and val:
            lines.append(f"  *{key}:* {val}")
    return lines


def format_verdict(verdict_dict: dict[str, Any]) -> str:
    """Convert a ``VerdictResponse`` dict into a WhatsApp message string."""
    v = verdict_dict.get("verdict", "unverifiable")
    score = verdict_dict.get("score", 0)
    summary = verdict_dict.get("summary", "")
    evidence = verdict_dict.get("evidence", [])
    label_fields = verdict_dict.get("label_fields", {})
    page_fields = verdict_dict.get("page_fields", {})
    ocr = verdict_dict.get("ocr")
    notes = verdict_dict.get("notes", [])

    all_fields = {**label_fields, **page_fields}
    field_lines = _format_fields(label_fields, page_fields)

    lines: list[str] = []

    # --- Special handling: unverifiable but we DID extract fields ---
    if v == "unverifiable" and all_fields:
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("  TrustLens — Label Scan")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("")
        lines.append("We read your medicine pack but couldn't find a QR/barcode URL to verify against the manufacturer's website.")
        lines.append("")
        lines.append("*Here's what we found on the label:*")
        lines.extend(field_lines)
        lines.append("")

        if ocr and ocr.get("text"):
            # Show a trimmed excerpt of the raw OCR text for transparency.
            raw = ocr["text"][:300].strip()
            lines.append("*Full text read from pack:*")
            lines.append(raw)
            lines.append("")

        lines.append("*What you can do:*")
        lines.append("  1. If there's a QR code, send a clearer photo of just the QR")
        lines.append("  2. Type the barcode number or URL printed on the pack")
        lines.append("  3. Ask me any questions about this medicine")
        lines.append("")
        lines.append(_DISCLAIMER)
        return "\n".join(lines)

    # --- Standard verified verdict ---
    icon = _VERDICT_ICON.get(v, "UNKNOWN")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("  TrustLens Verdict")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")

    if v == "unverifiable":
        lines.append(f"*{icon}* — Score: N/A")
    else:
        lines.append(f"*{icon}* — Score: {score}/10")
    lines.append("")

    if summary:
        lines.append(summary)
        lines.append("")

    if field_lines:
        lines.append("*What we found:*")
        lines.extend(field_lines)
        lines.append("")

    if evidence:
        lines.append("*Evidence:*")
        for e in evidence:
            lines.append(f"  {e}")
        lines.append("")

    # Notable warnings from pipeline notes
    warnings = [n for n in notes if n.get("severity") in ("warning", "error")]
    for w in warnings:
        lines.append(f"Note: {w.get('message', '')}")
    if warnings:
        lines.append("")

    # Footer
    lines.append("Ask me anything about this medicine, or send another photo to verify a new one.")
    lines.append("")
    lines.append(_DISCLAIMER)

    return "\n".join(lines)


def format_info_only(verdict_dict: dict[str, Any]) -> str:
    """Format an info-only response (code submitted, no image to compare)."""
    page_fields = verdict_dict.get("page_fields", {})
    page = verdict_dict.get("page")

    lines: list[str] = []
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("  TrustLens Info")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    lines.append("*INFO ONLY*")
    lines.append("")
    lines.append("Here's what the manufacturer's website says about this code.")
    lines.append("Compare it against the printed pack to confirm it matches.")
    lines.append("")

    if page_fields:
        lines.append("*Manufacturer page data:*")
        for key, val in page_fields.items():
            if val:
                lines.append(f"  *{key}:* {val}")
        lines.append("")

    if page and page.get("url"):
        lines.append(f"Source: {page['url']}")
        lines.append("")

    lines.append("Send a photo of the pack to get a full comparison verdict.")
    lines.append("")
    lines.append(_DISCLAIMER)

    return "\n".join(lines)


def format_welcome() -> str:
    """Welcome / usage hint for unrecognised messages."""
    return (
        "*Welcome to TrustLens!*\n"
        "\n"
        "I help you verify if your medicine is authentic and safe.\n"
        "\n"
        "*How to verify a medicine:*\n"
        "1. Send the medicine pack photo as a *Document* (not a photo)\n"
        "   → Tap attachment → *Document* → select your image\n"
        "   _(This keeps the image quality high for better accuracy)_\n"
        "2. Or *type* the barcode number or QR code URL\n"
        "\n"
        "I'll check it against the manufacturer's records and give you an instant verdict."
    )


def format_error(message: str) -> str:
    """Format an error message."""
    return (
        f"*TrustLens*\n"
        f"\n"
        f"{message}\n"
        f"\n"
        f"Please try again or send a different photo."
    )


def format_follow_up(answer: str) -> str:
    """Wrap a follow-up LLM answer with TrustLens branding."""
    return (
        f"*TrustLens*\n"
        f"\n"
        f"{answer}\n"
        f"\n"
        f"Ask another question or send a new photo.\n"
        f"\n"
        f"{_DISCLAIMER}"
    )
