"""
Prescription OCR pipeline.

Accepts a prescription image (raw bytes) or pre-extracted OCR text and returns:
  - Structured medicine list: name, dosage, frequency, duration
  - pgvector semantic search results for each medicine → matched DB cards
  - Doctor / patient metadata when the OCR is legible enough

Two-step design:
  1. Gemini Vision extracts structured JSON from the image (handles messy
     handwriting, stamps, abbreviations better than Tesseract).
  2. Each extracted medicine name is embedded and run through pgvector
     cosine-similarity search against ``medicines.name_embedding`` to resolve
     abbreviations ("Amox 500" → Amoxicillin 500mg), OCR noise, and brand vs
     generic name variations.

SCOPE GUARDRAIL:
  This pipeline shows what the prescription says and what TrustLens knows
  about those medicines. It NEVER suggests dosage changes, alternatives, or
  diagnoses. All output is prefixed with the disclaimer injected by the caller.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PrescribedMedicine:
    """One line item extracted from the prescription by Gemini."""
    raw_name: str                           # as written on the prescription
    dosage: str | None = None               # e.g. "500mg", "5ml"
    frequency: str | None = None            # e.g. "twice daily", "BD", "TDS"
    duration: str | None = None             # e.g. "5 days", "1 month"
    instructions: str | None = None         # e.g. "after food", "at night"


@dataclass
class MedicineCard:
    """
    Matched medicine from the DB paired with the prescription line item.

    ``match_score`` is the pgvector cosine similarity (0–1 range).
    A score below 0.60 usually means the medicine isn't in the DB —
    the card is still returned so the UI can show "not found in database".
    """
    prescribed: PrescribedMedicine
    db_medicine_id: str | None = None
    db_brand_name: str | None = None
    db_generic_name: str | None = None
    db_dosage_form: str | None = None
    db_manufacturer: str | None = None
    db_salts: list[str] = field(default_factory=list)
    match_score: float | None = None        # cosine similarity, 0–1
    found_in_db: bool = False


@dataclass
class PrescriptionExtractionResult:
    """Full output of the prescription pipeline for one image."""
    doctor_name: str | None = None
    patient_name: str | None = None
    prescription_date: str | None = None
    hospital_clinic: str | None = None
    medicine_cards: list[MedicineCard] = field(default_factory=list)
    raw_ocr_text: str = ""                  # full OCR text, for debugging
    extraction_method: str = "gemini"       # gemini | tesseract | unknown
    confidence: float | None = None         # overall OCR confidence
    notes: list[str] = field(default_factory=list)   # pipeline warnings / info


# ---------------------------------------------------------------------------
# Gemini extraction prompt
# ---------------------------------------------------------------------------

_PRESCRIPTION_EXTRACTION_PROMPT = """
You are a medical document parser. Extract all information from this prescription image.

Return ONLY a JSON object with this exact structure (no markdown, no explanation):
{
  "doctor_name": "<string or null>",
  "patient_name": "<string or null>",
  "prescription_date": "<DD/MM/YYYY or null>",
  "hospital_clinic": "<string or null>",
  "medicines": [
    {
      "name": "<medicine name as written>",
      "dosage": "<dose strength e.g. 500mg, 5ml, or null>",
      "frequency": "<e.g. once daily, BD, TDS, or null>",
      "duration": "<e.g. 5 days, 1 month, or null>",
      "instructions": "<e.g. after food, at bedtime, or null>"
    }
  ]
}

Rules:
- Preserve the medicine name exactly as written (abbreviations, brand names, etc.)
- If a field is not readable or not present, use null
- The medicines array must have at least one entry if any medicine is readable
- Do NOT interpret or suggest alternatives — extract only what is written
""".strip()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def extract_prescription(
    image_bytes: bytes,
    *,
    session: Any = None,        # AsyncSession — None skips DB vector search
    top_k: int = 1,             # how many DB matches to return per medicine
) -> PrescriptionExtractionResult:
    """Run the full prescription extraction pipeline.

    Steps:
      1. Call Gemini Vision to get structured JSON from the prescription image.
      2. For each extracted medicine name, run pgvector semantic search.
      3. Return a PrescriptionExtractionResult with all medicine cards.

    If Gemini is unavailable, falls back to raw Tesseract OCR + regex parsing.
    """
    logger.info("prescription.extract | image_size=%d bytes", len(image_bytes))

    # Step 1: Extract structure from image
    extracted = await _gemini_extract(image_bytes)
    if extracted is None:
        logger.warning("prescription.extract | Gemini failed, falling back to OCR")
        extracted = await _ocr_fallback_extract(image_bytes)

    result = PrescriptionExtractionResult(
        doctor_name=extracted.get("doctor_name"),
        patient_name=extracted.get("patient_name"),
        prescription_date=extracted.get("prescription_date"),
        hospital_clinic=extracted.get("hospital_clinic"),
        raw_ocr_text=extracted.get("_raw_text", ""),
        extraction_method=extracted.get("_method", "gemini"),
        confidence=extracted.get("_confidence"),
    )

    raw_medicines: list[dict] = extracted.get("medicines") or []
    logger.info("prescription.extract | found %d medicine entries", len(raw_medicines))

    # Step 2: For each medicine, resolve via pgvector search
    for med_dict in raw_medicines:
        prescribed = PrescribedMedicine(
            raw_name=med_dict.get("name") or "",
            dosage=med_dict.get("dosage"),
            frequency=med_dict.get("frequency"),
            duration=med_dict.get("duration"),
            instructions=med_dict.get("instructions"),
        )
        if not prescribed.raw_name.strip():
            continue

        card = await _resolve_medicine(prescribed, session=session, top_k=top_k)
        result.medicine_cards.append(card)
        logger.info(
            "prescription.resolve | raw=%r matched=%r score=%.3f",
            prescribed.raw_name,
            card.db_brand_name or card.db_generic_name or "not found",
            card.match_score or 0.0,
        )

    if not result.medicine_cards:
        result.notes.append("No medicines could be extracted from this image.")

    return result


# ---------------------------------------------------------------------------
# Gemini extraction
# ---------------------------------------------------------------------------

async def _gemini_extract(image_bytes: bytes) -> dict | None:
    """Use Gemini Vision to extract structured JSON from the prescription."""
    from app.core.config import get_settings
    settings = get_settings()

    if not settings.google_api_key:
        logger.info("prescription._gemini_extract | GOOGLE_API_KEY not set, skipping")
        return None

    try:
        import google.generativeai as genai  # type: ignore[import]
        import PIL.Image as PILImage
        import io

        genai.configure(api_key=settings.google_api_key)
        model = genai.GenerativeModel(settings.google_vision_model)

        image = PILImage.open(io.BytesIO(image_bytes))
        response = model.generate_content([_PRESCRIPTION_EXTRACTION_PROMPT, image])

        text = response.text.strip()
        # Strip markdown code fences if Gemini wraps in ```json ... ```
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()

        parsed = json.loads(text)
        parsed["_method"] = "gemini"
        logger.info(
            "prescription._gemini_extract | ok medicines=%d",
            len(parsed.get("medicines") or []),
        )
        return parsed

    except json.JSONDecodeError as exc:
        logger.warning("prescription._gemini_extract | JSON parse failed: %s", exc)
        return None
    except Exception as exc:
        logger.warning("prescription._gemini_extract | Gemini call failed: %s", exc)
        return None


async def _ocr_fallback_extract(image_bytes: bytes) -> dict:
    """Tesseract OCR + simple regex parsing as Gemini fallback."""
    from services.ocr.extractor import extract_text

    ocr_result = await extract_text(image_bytes)
    raw_text = (ocr_result.text if ocr_result else "") or ""
    logger.info("prescription._ocr_fallback | chars=%d", len(raw_text))

    medicines = _parse_medicines_from_text(raw_text)
    return {
        "doctor_name": None,
        "patient_name": None,
        "prescription_date": None,
        "hospital_clinic": None,
        "medicines": medicines,
        "_raw_text": raw_text,
        "_method": "tesseract",
        "_confidence": ocr_result.confidence if ocr_result else None,
    }


def _parse_medicines_from_text(text: str) -> list[dict]:
    """
    Heuristic extraction when Gemini isn't available.

    Looks for lines matching "medicine name [dosage] [frequency]" patterns
    common on typed (not handwritten) Indian prescriptions.
    """
    import re

    if not text:
        return []

    # Dosage pattern: 100mg, 500 mg, 5ml, 10 mL
    _DOSE_RE = re.compile(r"\b(\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|IU))\b", re.IGNORECASE)
    # Frequency keywords
    _FREQ_RE = re.compile(
        r"\b(od|bd|tds|qid|once\s+daily|twice\s+daily|thrice\s+daily|"
        r"1[\-\s]?0[\-\s]?0|1[\-\s]?1[\-\s]?0|1[\-\s]?1[\-\s]?1|"
        r"morning|night|bedtime|sos|as\s+needed)\b",
        re.IGNORECASE,
    )

    medicines = []
    for line in text.splitlines():
        line = line.strip()
        if len(line) < 3:
            continue
        # Skip lines that look like headers, addresses, dates
        if re.match(r"^(dr\.?|patient|name|date|age|rx|address|\d{1,2}/\d{1,2})", line, re.IGNORECASE):
            continue

        dose_m = _DOSE_RE.search(line)
        freq_m = _FREQ_RE.search(line)

        # Treat any line with a dosage as a medicine line
        if dose_m or (freq_m and len(line) > 5):
            name_end = dose_m.start() if dose_m else (freq_m.start() if freq_m else len(line))
            name = line[:name_end].strip(" .,:-")
            if name and len(name) >= 3:
                medicines.append({
                    "name": name,
                    "dosage": dose_m.group(1) if dose_m else None,
                    "frequency": freq_m.group(1) if freq_m else None,
                    "duration": None,
                    "instructions": None,
                })

    return medicines


# ---------------------------------------------------------------------------
# pgvector semantic search
# ---------------------------------------------------------------------------

async def _resolve_medicine(
    prescribed: PrescribedMedicine,
    *,
    session: Any,
    top_k: int = 1,
) -> MedicineCard:
    """Embed the medicine name and run a cosine-similarity search."""
    card = MedicineCard(prescribed=prescribed)

    if session is None:
        logger.debug("prescription._resolve_medicine | no session, skipping DB lookup")
        return card

    try:
        embedding = await _embed_text(prescribed.raw_name)
        if not embedding:
            return card

        matches = await _vector_search(session, embedding, top_k=top_k)
        if not matches:
            logger.info(
                "prescription._resolve_medicine | no DB match for %r",
                prescribed.raw_name,
            )
            return card

        best = matches[0]
        card.db_medicine_id = str(best["id"])
        card.db_brand_name = best.get("brand_name")
        card.db_generic_name = best.get("generic_name")
        card.db_dosage_form = best.get("dosage_form")
        card.db_manufacturer = best.get("manufacturer_name")
        card.db_salts = best.get("salts") or []
        card.match_score = float(best.get("similarity") or 0.0)
        card.found_in_db = card.match_score >= 0.55   # below 0.55 = likely not in DB

    except Exception as exc:
        logger.warning(
            "prescription._resolve_medicine | DB lookup failed for %r: %s",
            prescribed.raw_name, exc,
        )

    return card


async def _embed_text(text: str) -> list[float] | None:
    """Generate an OpenAI text embedding for the medicine name."""
    from app.core.config import get_settings
    settings = get_settings()

    if not settings.openai_api_key:
        logger.debug("prescription._embed_text | OPENAI_API_KEY not set, skipping")
        return None

    try:
        import openai
        client = openai.AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )
        response = await client.embeddings.create(
            model=settings.embedding_model,
            input=text.strip(),
        )
        return response.data[0].embedding

    except Exception as exc:
        logger.warning("prescription._embed_text | embedding failed: %s", exc)
        return None


async def _vector_search(session: Any, embedding: list[float], *, top_k: int) -> list[dict]:
    """
    Run a pgvector cosine-similarity query on medicines.name_embedding.

    Returns a list of dicts sorted by similarity descending. Each dict has:
      id, brand_name, generic_name, dosage_form, manufacturer_name,
      salts (list[str]), similarity (float)

    The raw SQL is necessary here because SQLAlchemy's ORM doesn't yet have
    a first-class pgvector operator; we use the ``<=>`` (cosine distance)
    operator directly and convert to similarity = 1 - distance.
    """
    import sqlalchemy as sa

    # Represent the query vector as a Postgres array literal for the <=> operator
    vec_literal = "[" + ",".join(str(v) for v in embedding) + "]"

    sql = sa.text("""
        SELECT
            m.id,
            m.brand_name,
            m.generic_name,
            m.dosage_form,
            m.manufacturer_name,
            ARRAY_AGG(s.name) FILTER (WHERE s.name IS NOT NULL) AS salts,
            1 - (m.name_embedding::vector <=> :vec::vector) AS similarity
        FROM medicines m
        LEFT JOIN medicine_salts ms ON ms.medicine_id = m.id
        LEFT JOIN salts s           ON s.id = ms.salt_id
        WHERE m.name_embedding IS NOT NULL
        GROUP BY m.id
        ORDER BY m.name_embedding::vector <=> :vec::vector
        LIMIT :top_k
    """)

    try:
        result = await session.execute(sql, {"vec": vec_literal, "top_k": top_k})
        rows = result.mappings().all()
        return [dict(r) for r in rows]
    except Exception as exc:
        # pgvector might not be enabled or name_embedding might be Text placeholder
        logger.warning("prescription._vector_search | query failed: %s", exc)
        return []
