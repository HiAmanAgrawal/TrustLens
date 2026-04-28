"""
Vision-LLM structured product extraction for grocery labels.

WHY this module exists:
  Regex-based OCR parsing fails on ingredient counts because real-world labels
  print ingredients as a run-on paragraph, and OCR drift moves section headers
  around. Asking a vision LLM to parse the *whole image* directly returns a
  structured JSON response in one shot.

FALLBACK CHAIN (tried in order, first success wins):
  1. Google Gemini Vision   — GOOGLE_API_KEY (cloud, best accuracy)
  2. LM Studio Qwen VL      — LM_STUDIO_BASE_URL / LM_STUDIO_VISION_MODEL
                               (local, private, no data leaves the machine)
  3. OpenAI cloud vision    — OPENAI_API_KEY + OPENAI_BASE_URL (gpt-4o-mini)
  4. ProductExtraction(extraction_method="failed") — never raises

LM Studio setup (Qwen2.5-VL / Qwen3-VL):
  1. Download the model in LM Studio → Load it
  2. Start the local server (default: http://localhost:1234)
  3. Set in .env:
       LM_STUDIO_BASE_URL=http://localhost:1234/v1
       LM_STUDIO_VISION_MODEL=qwen2.5-vl-7b-instruct   # match LM Studio model name
  4. No API key needed — LM_STUDIO_API_KEY can be any non-empty string.

  LM Studio health check: a 2-second GET /models ping is done before sending
  the full image so failures are reported instantly, not after a long timeout.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_EXTRACTION_PROMPT = """You are a grocery product label reader. Analyze this image and extract ALL visible information as JSON.

Return EXACTLY this JSON structure (use null for missing fields, empty arrays for missing lists):

{
  "brand_name": "string or null",
  "product_name": "string or null",
  "product_type": "snack|beverage|dairy|grain|condiment|confectionery|personal_care|other or null",
  "ingredients": ["ingredient1", "ingredient2"],
  "ingredients_count": integer or null,
  "nutrition_per_100g": {
    "calories_kcal": number or null,
    "protein_g": number or null,
    "total_fat_g": number or null,
    "saturated_fat_g": number or null,
    "carbohydrates_g": number or null,
    "sugar_g": number or null,
    "dietary_fiber_g": number or null,
    "sodium_mg": number or null
  },
  "serving_size": "string or null",
  "servings_per_pack": number or null,
  "positives": ["e.g. high fiber", "no artificial preservatives"],
  "negatives": ["e.g. high sugar (15g/100g)", "contains palm oil"],
  "allergens_declared": ["peanuts", "milk"],
  "certifications": ["FSSAI", "ISO", "Organic", "Vegan"],
  "fssai_license": "14-digit number or null",
  "best_before": "date string or null",
  "manufactured_date": "date string or null",
  "expiry_date": "date string or null",
  "storage_instructions": "string or null",
  "net_weight": "string or null",
  "country_of_origin": "string or null",
  "manufacturer": "string or null",
  "e_codes_found": ["E102", "E211"],
  "is_vegetarian": true or false or null,
  "is_vegan": true or false or null,
  "is_gluten_free": true or false or null,
  "contains_added_sugar": true or false or null,
  "contains_preservatives": true or false or null,
  "contains_artificial_colours": true or false or null
}

Rules:
- Extract EVERY ingredient you can see, even partially visible ones.
- For nutrition use per-100g values. If only per-serving is shown, convert using the serving size.
- Positives = genuinely good attributes (high protein, whole grain, no preservatives, low sodium).
- Negatives = health concerns (high sugar >10g/100g, high sodium >400mg/100g, trans fat, palm oil, concerning E-codes).
- is_vegetarian: true if green dot / "Veg" symbol or only plant ingredients visible.
- Do NOT guess — only extract what is actually visible on the label.
- Return ONLY the JSON object. No markdown fences, no explanation, no extra text."""


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class NutritionInfo:
    calories_kcal: float | None = None
    protein_g: float | None = None
    total_fat_g: float | None = None
    saturated_fat_g: float | None = None
    carbohydrates_g: float | None = None
    sugar_g: float | None = None
    dietary_fiber_g: float | None = None
    sodium_mg: float | None = None


@dataclass
class ProductExtraction:
    """
    Rich product data extracted directly from the label image by a vision LLM.

    This is the complement to the rule-based GroceryAnalysis — it fills in
    structured fields (ingredients list, nutrition, diet flags) that regex
    patterns struggle with on real-world OCR output.
    """
    brand_name: str | None = None
    product_name: str | None = None
    product_type: str | None = None
    ingredients: list[str] = field(default_factory=list)
    ingredients_count: int | None = None
    nutrition: NutritionInfo = field(default_factory=NutritionInfo)
    serving_size: str | None = None
    servings_per_pack: float | None = None
    positives: list[str] = field(default_factory=list)
    negatives: list[str] = field(default_factory=list)
    allergens_declared: list[str] = field(default_factory=list)
    certifications: list[str] = field(default_factory=list)
    fssai_license: str | None = None
    best_before: str | None = None
    manufactured_date: str | None = None
    expiry_date: str | None = None
    storage_instructions: str | None = None
    net_weight: str | None = None
    country_of_origin: str | None = None
    manufacturer: str | None = None
    e_codes_found: list[str] = field(default_factory=list)
    is_vegetarian: bool | None = None
    is_vegan: bool | None = None
    is_gluten_free: bool | None = None
    contains_added_sugar: bool | None = None
    contains_preservatives: bool | None = None
    contains_artificial_colours: bool | None = None
    extraction_method: str = "unknown"  # gemini | lm_studio | openai_cloud | failed


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def extract_product_info(image_bytes: bytes) -> ProductExtraction:
    """
    Extract structured product info from a grocery label image.

    Fallback chain: Gemini → LM Studio (Qwen VL) → OpenAI cloud.
    Never raises — returns ProductExtraction(extraction_method="failed") if all fail.
    """
    logger.info("gemini_extract.start | bytes=%d", len(image_bytes))

    # 1. Gemini Vision
    result = await _try_gemini(image_bytes)
    if result is not None:
        logger.info(
            "gemini_extract.done | method=gemini brand=%r ingredients=%s",
            result.brand_name, result.ingredients_count,
        )
        return result

    # 2. LM Studio with Qwen VL
    result = await _try_lm_studio(image_bytes)
    if result is not None:
        logger.info(
            "gemini_extract.done | method=lm_studio brand=%r ingredients=%s",
            result.brand_name, result.ingredients_count,
        )
        return result

    # 3. OpenAI cloud (gpt-4o-mini)
    result = await _try_openai_cloud(image_bytes)
    if result is not None:
        logger.info(
            "gemini_extract.done | method=openai_cloud brand=%r ingredients=%s",
            result.brand_name, result.ingredients_count,
        )
        return result

    logger.warning("gemini_extract.done | method=failed — all providers exhausted")
    return ProductExtraction(extraction_method="failed")


# ---------------------------------------------------------------------------
# Provider 1: Google Gemini Vision
# ---------------------------------------------------------------------------

async def _try_gemini(image_bytes: bytes) -> ProductExtraction | None:
    """
    Gemini Vision via google-genai SDK.
    Requires GOOGLE_API_KEY. Uses GOOGLE_VISION_MODEL (default: gemini-2.5-flash).
    """
    try:
        from app.core.config import get_settings
        s = get_settings()
        if not s.google_api_key:
            logger.debug("gemini_extract._gemini | skipped (no GOOGLE_API_KEY)")
            return None

        import io
        import PIL.Image
        import google.generativeai as genai

        genai.configure(api_key=s.google_api_key)
        model = genai.GenerativeModel(s.google_vision_model)
        pil_img = PIL.Image.open(io.BytesIO(image_bytes))

        logger.info("gemini_extract._gemini | calling model=%s", s.google_vision_model)
        response = model.generate_content(
            [_EXTRACTION_PROMPT, pil_img],
            generation_config={"temperature": 0.1, "max_output_tokens": 2048},
        )
        return _parse(response.text.strip(), method="gemini")

    except Exception as exc:
        logger.warning("gemini_extract._gemini | failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Provider 2: LM Studio — Qwen VL (local, privacy-preserving)
# ---------------------------------------------------------------------------

async def _lm_studio_is_running(base_url: str, timeout: float) -> bool:
    """
    Quick health-check: GET {base_url}/models with a short timeout.
    Returns True if LM Studio responds within ``timeout`` seconds.

    WHY a health check before the full call:
      Without this, a connection-refused error takes the full inference timeout
      (60 s) to surface. A 2-second ping fails fast so we can move to the next
      provider immediately.
    """
    import httpx
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(f"{base_url}/models")
            alive = r.status_code < 500
            logger.debug(
                "gemini_extract._lm_studio_health | url=%s status=%d alive=%s",
                base_url, r.status_code, alive,
            )
            return alive
    except Exception as exc:
        logger.debug("gemini_extract._lm_studio_health | unreachable: %s", exc)
        return False


async def _try_lm_studio(image_bytes: bytes) -> ProductExtraction | None:
    """
    LM Studio local vision model (Qwen2.5-VL / Qwen3-VL or any loaded VL model).

    Steps:
      1. Quick 2-second health check — skip if LM Studio is not running.
      2. Encode image as base64 data URL.
      3. Send vision chat completion request using the OpenAI-compatible API.
      4. Parse JSON response.

    Model name must match what is currently loaded in LM Studio.
    Set LM_STUDIO_VISION_MODEL in .env to override the default.
    """
    try:
        from app.core.config import get_settings
        s = get_settings()

        base_url = s.lm_studio_base_url
        model = s.lm_studio_vision_model

        # Health check first — fail fast if LM Studio is not running
        if not await _lm_studio_is_running(base_url, s.lm_studio_health_timeout_s):
            logger.info(
                "gemini_extract._lm_studio | skipped (server not reachable @ %s)", base_url,
            )
            return None

        import base64
        from openai import AsyncOpenAI

        b64 = base64.b64encode(image_bytes).decode()
        client = AsyncOpenAI(
            api_key=s.lm_studio_api_key,
            base_url=base_url,
            timeout=s.lm_studio_timeout_s,
        )

        logger.info(
            "gemini_extract._lm_studio | calling model=%s @ %s", model, base_url,
        )
        resp = await client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": _EXTRACTION_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                    },
                ],
            }],
            temperature=0.1,
            max_tokens=2048,
        )
        raw = (resp.choices[0].message.content or "").strip()
        logger.info(
            "gemini_extract._lm_studio | response received len=%d", len(raw),
        )
        return _parse(raw, method="lm_studio")

    except Exception as exc:
        logger.warning("gemini_extract._lm_studio | failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Provider 3: OpenAI cloud (gpt-4o-mini)
# ---------------------------------------------------------------------------

async def _try_openai_cloud(image_bytes: bytes) -> ProductExtraction | None:
    """
    OpenAI cloud vision via gpt-4o-mini.
    Requires OPENAI_API_KEY. Skipped if OPENAI_BASE_URL points to localhost
    (which means the user has LM Studio configured there already).
    """
    try:
        from app.core.config import get_settings
        s = get_settings()

        if not s.openai_api_key:
            logger.debug("gemini_extract._openai_cloud | skipped (no OPENAI_API_KEY)")
            return None

        # Don't use this provider if base_url is local — that's LM Studio territory
        if "localhost" in s.openai_base_url or "127.0.0.1" in s.openai_base_url:
            logger.debug(
                "gemini_extract._openai_cloud | skipped (OPENAI_BASE_URL=%s is local; "
                "use LM_STUDIO_* vars instead)",
                s.openai_base_url,
            )
            return None

        import base64
        from openai import AsyncOpenAI

        b64 = base64.b64encode(image_bytes).decode()
        client = AsyncOpenAI(api_key=s.openai_api_key, base_url=s.openai_base_url)

        logger.info(
            "gemini_extract._openai_cloud | calling gpt-4o-mini @ %s", s.openai_base_url,
        )
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": _EXTRACTION_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                    },
                ],
            }],
            temperature=0.1,
            max_tokens=2048,
        )
        raw = (resp.choices[0].message.content or "").strip()
        return _parse(raw, method="openai_cloud")

    except Exception as exc:
        logger.warning("gemini_extract._openai_cloud | failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# JSON parser
# ---------------------------------------------------------------------------

def _parse(raw: str, *, method: str) -> ProductExtraction | None:
    """Parse the LLM JSON response into a ProductExtraction. Returns None on failure."""
    try:
        # Strip markdown code fences that some models include despite instructions
        text = raw
        if "```" in text:
            import re
            m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
            text = m.group(1) if m else text.replace("```json", "").replace("```", "")

        data = json.loads(text.strip())

        # Build nutrition sub-object
        n = data.get("nutrition_per_100g") or {}
        nutrition = NutritionInfo(
            calories_kcal=_num(n.get("calories_kcal")),
            protein_g=_num(n.get("protein_g")),
            total_fat_g=_num(n.get("total_fat_g")),
            saturated_fat_g=_num(n.get("saturated_fat_g")),
            carbohydrates_g=_num(n.get("carbohydrates_g")),
            sugar_g=_num(n.get("sugar_g")),
            dietary_fiber_g=_num(n.get("dietary_fiber_g")),
            sodium_mg=_num(n.get("sodium_mg")),
        )

        ingredients = data.get("ingredients") or []
        if not isinstance(ingredients, list):
            ingredients = []
        ing_count = data.get("ingredients_count")
        # Always derive count from list if Gemini didn't provide it
        if (ing_count is None) and ingredients:
            ing_count = len(ingredients)

        return ProductExtraction(
            brand_name=_str(data.get("brand_name")),
            product_name=_str(data.get("product_name")),
            product_type=_str(data.get("product_type")),
            ingredients=ingredients,
            ingredients_count=ing_count,
            nutrition=nutrition,
            serving_size=_str(data.get("serving_size")),
            servings_per_pack=_num(data.get("servings_per_pack")),
            positives=data.get("positives") or [],
            negatives=data.get("negatives") or [],
            allergens_declared=data.get("allergens_declared") or [],
            certifications=data.get("certifications") or [],
            fssai_license=_str(data.get("fssai_license")),
            best_before=_str(data.get("best_before")),
            manufactured_date=_str(data.get("manufactured_date")),
            expiry_date=_str(data.get("expiry_date")),
            storage_instructions=_str(data.get("storage_instructions")),
            net_weight=_str(data.get("net_weight")),
            country_of_origin=_str(data.get("country_of_origin")),
            manufacturer=_str(data.get("manufacturer")),
            e_codes_found=data.get("e_codes_found") or [],
            is_vegetarian=data.get("is_vegetarian"),
            is_vegan=data.get("is_vegan"),
            is_gluten_free=data.get("is_gluten_free"),
            contains_added_sugar=data.get("contains_added_sugar"),
            contains_preservatives=data.get("contains_preservatives"),
            contains_artificial_colours=data.get("contains_artificial_colours"),
            extraction_method=method,
        )
    except Exception as exc:
        logger.warning("gemini_extract._parse | failed method=%s err=%s raw=%r", method, exc, raw[:200])
        return None


# ---------------------------------------------------------------------------
# Tiny converters
# ---------------------------------------------------------------------------

def _str(v: object) -> str | None:
    if v is None or v == "null":
        return None
    s = str(v).strip()
    return s if s else None


def _num(v: object) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None
