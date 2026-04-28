"""Format pipeline responses into WhatsApp-friendly plain text.

WhatsApp supports a small subset of formatting:
- *bold*  (single asterisks)
- _italic_ (single underscores)
- ~strikethrough~ (single tildes)
- ```monospace``` (triple backticks)

We stick to *bold* and plain text so messages render cleanly on all devices.

Two formatter groups live here:
  1. Legacy medicine verdict formatters  (format_verdict, format_info_only, …)
  2. Phase 3 pipeline formatters         (format_grocery_scan, format_medicine_scan,
                                          format_prescription_scan, format_advisor_reply)
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
        "*Welcome to TrustLens!* 🔍\n"
        "\n"
        "I help you verify medicines and grocery products.\n"
        "\n"
        "*📷 Send a photo to:*\n"
        "• Check if a medicine is authentic & safe\n"
        "• Analyse a grocery product (ingredients, nutrition, FSSAI)\n"
        "• Read a prescription and match medicines in our database\n"
        "\n"
        "After scanning, ask me anything:\n"
        "_\"Is this safe for diabetics?\"_\n"
        "_\"Does this have allergens?\"_\n"
        "_\"How many calories per serving?\"_\n"
        "\n"
        "Or *type* a barcode number / QR code URL to verify a medicine directly."
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


# ---------------------------------------------------------------------------
# Phase 3 pipeline formatters
# ---------------------------------------------------------------------------

_RISK_LABEL = {
    "low":     "✅ LOW RISK",
    "medium":  "⚠️ MEDIUM RISK",
    "high":    "❌ HIGH RISK",
    "unknown": "❓ UNKNOWN",
}

_EXPIRY_LABEL = {
    "SAFE":        "✅ SAFE",
    "NEAR_EXPIRY": "⚠️ NEAR EXPIRY (<30 days)",
    "EXPIRED":     "❌ EXPIRED",
    "UNKNOWN":     "❓ UNKNOWN",
}

_VERDICT_LABEL = {
    "VERIFIED":   "✅ VERIFIED",
    "SUSPICIOUS": "⚠️ SUSPICIOUS",
    "EXPIRED":    "❌ EXPIRED",
    "UNKNOWN":    "❓ UNKNOWN",
}


def format_grocery_scan(result: Any) -> str:
    """
    Format a GroceryScanResponse (pydantic model or dict) into a WhatsApp message.

    Prioritises the Gemini-extracted product info (brand, flags, nutrition concerns)
    over the raw ingredient list so the message stays under ~1200 chars.
    """
    r: dict = result if isinstance(result, dict) else result.model_dump(mode="json")
    pe: dict = r.get("product_extraction") or {}

    brand   = pe.get("brand_name") or pe.get("product_name") or "Unknown product"
    product = pe.get("product_name") or ""
    risk    = r.get("risk_band") or "unknown"
    expiry  = r.get("expiry_status") or "UNKNOWN"

    lines: list[str] = [
        "━━━━━━━━━━━━━━━━━━━━━━",
        "  TrustLens — Grocery Scan",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"📦 *{brand}*",
    ]
    if product and product != brand:
        lines.append(product)
    lines += ["", f"*Risk:* {_RISK_LABEL.get(risk, risk.upper())}",
              f"*Expiry:* {_EXPIRY_LABEL.get(expiry, expiry)}", ""]

    # Diet / additive flags (compact, single line)
    flags: list[str] = []
    if pe.get("is_vegetarian") is True:            flags.append("🟢 Veg")
    if pe.get("is_vegan") is True:                 flags.append("🌱 Vegan")
    if pe.get("is_gluten_free") is True:           flags.append("🚫 Gluten-free")
    if pe.get("contains_added_sugar") is True:     flags.append("🍬 Added sugar")
    if pe.get("contains_preservatives") is True:   flags.append("⚗️ Preservatives")
    if pe.get("contains_artificial_colours") is True: flags.append("🎨 Art. colours")
    if flags:
        lines.append(" · ".join(flags))
        lines.append("")

    # Ingredients count
    ing_count = r.get("ingredients_count")
    if not ing_count and pe.get("ingredients"):
        ing_count = len(pe["ingredients"])
    if ing_count:
        lines.append(f"🧪 *{ing_count} ingredients*")
        lines.append("")

    # Allergen warnings (cross-checked against user profile if available)
    allergens = r.get("allergen_warnings") or []
    if allergens:
        lines.append("*⚠️ Allergen Warnings:*")
        for a in allergens[:4]:
            lines.append(f"  🚫 {a}")
        lines.append("")

    # Top findings (errors + warnings only, capped at 3)
    findings = r.get("findings") or []
    top = [f for f in findings if f.get("severity") in ("error", "warning")][:3]
    if top:
        sev_icon = {"error": "❌", "warning": "⚠️"}
        lines.append("*Key Findings:*")
        for f in top:
            lines.append(f"  {sev_icon.get(f.get('severity'), '•')} {f.get('message', '')}")
        lines.append("")

    # FSSAI status
    fssai = r.get("fssai") or {}
    if fssai:
        lic = fssai.get("license_number") or ""
        status = fssai.get("online_status") or "unknown"
        if status == "valid":
            lines.append(f"✅ FSSAI verified (#{lic})" if lic else "✅ FSSAI verified")
        elif status == "invalid":
            lines.append(f"❌ FSSAI invalid (#{lic})" if lic else "❌ FSSAI invalid")
        else:
            lines.append(f"❓ FSSAI #{lic} — {status}" if lic else f"❓ FSSAI {status}")
        lines.append("")

    # Gemini positives / negatives (top 2 each)
    positives = pe.get("positives") or []
    negatives = pe.get("negatives") or []
    if positives or negatives:
        lines.append("*Analysis:*")
        for p in positives[:2]:
            lines.append(f"  ✅ {p}")
        for n in negatives[:2]:
            lines.append(f"  ⚠️ {n}")
        lines.append("")

    lines += [
        "*Ask me anything about this product:*",
        '_"Is this safe for diabetics?"_',
        '_"How often can I eat this?"_',
        '_"What are the main concerns?"_',
        "",
        "_TrustLens is an AI tool — not a substitute for dietitian advice._",
    ]
    return "\n".join(lines)


def format_medicine_scan(result: Any) -> str:
    """
    Format a Phase 3 MedicineScanResponse for WhatsApp.

    Uses the Phase 3 verdict/expiry/storage fields (different schema from
    the legacy VerdictResponse used by format_verdict).
    """
    r: dict = result if isinstance(result, dict) else result.model_dump(mode="json")

    brand        = r.get("brand_name") or "Unknown medicine"
    generic      = r.get("generic_name") or ""
    manufacturer = r.get("manufacturer_name") or ""
    verdict      = r.get("verdict") or "UNKNOWN"
    expiry       = r.get("expiry_status") or "UNKNOWN"
    summary      = r.get("verdict_summary") or ""

    lines: list[str] = [
        "━━━━━━━━━━━━━━━━━━━━━━",
        "  TrustLens — Medicine Scan",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"💊 *{brand}*",
    ]
    if generic:
        lines.append(generic)
    if manufacturer:
        lines.append(f"_{manufacturer}_")
    lines += [
        "",
        f"*Verdict:* {_VERDICT_LABEL.get(verdict, verdict)}",
        f"*Expiry:* {_EXPIRY_LABEL.get(expiry, expiry)}",
    ]
    if summary:
        lines += ["", summary]
    lines.append("")

    # Storage warnings
    for w in (r.get("storage_warnings") or [])[:2]:
        lines.append(f"📦 {w.get('message') or w.get('condition', '')}")
    if r.get("storage_warnings"):
        lines.append("")

    lines += [
        "Ask me anything about this medicine, or send another photo.",
        "",
        _DISCLAIMER,
    ]
    return "\n".join(lines)


def format_prescription_scan(result: Any) -> str:
    """Format a Phase 3 PrescriptionScanResponse for WhatsApp."""
    r: dict = result if isinstance(result, dict) else result.model_dump(mode="json")

    lines: list[str] = [
        "━━━━━━━━━━━━━━━━━━━━━━",
        "  TrustLens — Prescription",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    doctor  = r.get("doctor_name") or ""
    patient = r.get("patient_name") or ""
    if doctor:  lines.append(f"👨‍⚕️ Dr. {doctor}")
    if patient: lines.append(f"🧑 Patient: {patient}")
    if doctor or patient: lines.append("")

    cards = r.get("medicine_cards") or []
    if cards:
        lines.append(f"*Medicines found ({len(cards)}):*")
        for c in cards:
            prescribed = c.get("prescribed") or {}
            name   = prescribed.get("raw_name") or "Unknown"
            dosage = prescribed.get("dosage") or ""
            freq   = prescribed.get("frequency") or ""
            found  = c.get("found_in_db", False)
            status = "✅" if found else "❓"
            detail = f"  {status} {name}"
            if dosage: detail += f" — {dosage}"
            if freq:   detail += f" ({freq})"
            lines.append(detail)
        lines.append("")

    lines += [
        "Send a photo of any medicine from this prescription to verify it.",
        "",
        _DISCLAIMER,
    ]
    return "\n".join(lines)


def format_advisor_reply(answer: str, tools_called: list[str] | None = None) -> str:
    """
    Wrap a LangGraph product advisor answer for WhatsApp.

    Converts **markdown bold** to WhatsApp *bold* and appends tool
    transparency and a standard disclaimer.
    """
    # **text** → *text* (WhatsApp bold)
    formatted = answer.replace("**", "*")

    lines: list[str] = [
        "*TrustLens Advisor*",
        "",
        formatted,
        "",
    ]

    if tools_called:
        _tool_label = {
            "search_web":          "web search",
            "assess_suitability":  "health check",
            "calculate_trust_score": "trust scoring",
            "lookup_product_db":   "product DB",
        }
        readable = [_tool_label.get(t, t) for t in tools_called[:3]]
        if readable:
            lines.append(f"_Checked via: {', '.join(readable)}_")
            lines.append("")

    lines += [
        "Ask another question or send a new photo to scan a product.",
        "",
        _DISCLAIMER,
    ]
    return "\n".join(lines)
