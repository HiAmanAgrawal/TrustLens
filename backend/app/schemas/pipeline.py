"""
Phase 3 unified pipeline API schemas.

One schema per pipeline type:
  PrescriptionScanResponse  — prescription image → medicine cards
  MedicineScanResponse      — medicine barcode/image → verify result
  GroceryScanResponse       — grocery image → safety analysis
  UnifiedScanResponse       — auto-classified → any of the above

All responses are wrapped in TrustLensResponse[T] at the route level.

IMPORTANT: These schemas are read-only (response only). Input validation
  is handled by FastAPI's form/file parameters in the route layer.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Common sub-schemas
# ---------------------------------------------------------------------------

class StorageWarningSchema(BaseModel):
    """One storage instruction extracted from the label."""
    condition: str          # e.g. "refrigerate", "away_from_children"
    message: str            # human-readable English text
    severity: Literal["info", "warning"]
    raw_text: str = ""      # matched OCR snippet


class BatchInfoSchema(BaseModel):
    """Batch-level medicine identity resolved from the DB."""
    batch_id: str
    batch_number: str | None
    expiry_date: date | None
    manufacture_date: date | None
    is_expired: bool


# ---------------------------------------------------------------------------
# Prescription pipeline schemas
# ---------------------------------------------------------------------------

class PrescribedMedicineSchema(BaseModel):
    """One medicine line item extracted from the prescription."""
    raw_name: str
    dosage: str | None = None
    frequency: str | None = None
    duration: str | None = None
    instructions: str | None = None


class MedicineCardSchema(BaseModel):
    """
    A prescribed medicine paired with its best DB match.

    ``found_in_db`` is False when no match with score ≥ 0.55 was found.
    The UI should show the raw_name in that case with a "not in database" badge.
    """
    prescribed: PrescribedMedicineSchema
    db_medicine_id: str | None = None
    db_brand_name: str | None = None
    db_generic_name: str | None = None
    db_dosage_form: str | None = None
    db_manufacturer: str | None = None
    db_salts: list[str] = Field(default_factory=list)
    match_score: float | None = Field(None, description="pgvector cosine similarity (0–1)")
    found_in_db: bool = False


class PrescriptionScanResponse(BaseModel):
    """Response for POST /v1/scan/prescription."""
    scan_type: Literal["prescription"] = "prescription"
    doctor_name: str | None = None
    patient_name: str | None = None
    prescription_date: str | None = None
    hospital_clinic: str | None = None
    medicine_cards: list[MedicineCardSchema] = Field(default_factory=list)
    extraction_method: str = Field(description="gemini | tesseract | unknown")
    confidence: float | None = None
    disclaimer: str = Field(
        default=(
            "TrustLens identifies medicines on prescriptions for information only. "
            "Never alter dosage or frequency without your doctor's advice."
        ),
    )
    notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Medicine verification schemas
# ---------------------------------------------------------------------------

class MedicineScanResponse(BaseModel):
    """Response for POST /v1/scan/image or /v1/scan/code (pharma path)."""
    scan_type: Literal["medicine"] = "medicine"
    scan_event_id: str | None = None       # MedicineScanEvent UUID, after DB persist

    # Verdict
    verdict: Literal["VERIFIED", "SUSPICIOUS", "EXPIRED", "UNKNOWN"]
    verdict_score: float | None = Field(None, ge=0, le=10)
    verdict_summary: str = ""

    # Product identity
    medicine_id: str | None = None
    brand_name: str | None = None
    generic_name: str | None = None
    manufacturer_name: str | None = None
    batch_info: BatchInfoSchema | None = None

    # Expiry status
    expiry_status: Literal["SAFE", "NEAR_EXPIRY", "EXPIRED", "UNKNOWN"] = "UNKNOWN"

    # Data sources used
    source: str = Field(description="db+scraper|db+tavily|db_only|matcher_only|unknown")
    tavily_used: bool = False

    # Storage
    storage_warnings: list[StorageWarningSchema] = Field(default_factory=list)

    # Transparency
    notes: list[str] = Field(default_factory=list)

    # Structured fields extracted from OCR (populated for image-only scans)
    extracted_label: dict[str, Any] | None = Field(
        default=None,
        description="Structured label fields parsed by Gemini: brand, salt, batch, expiry, manufacturer",
    )
    ocr_text: str | None = Field(
        default=None,
        description="Raw OCR text extracted from the label image",
    )


# ---------------------------------------------------------------------------
# Grocery verification schemas
# ---------------------------------------------------------------------------

class FssaiVerifySchema(BaseModel):
    """FSSAI license verification result."""
    license_number: str | None = None
    format_valid: bool = False
    online_status: str = Field(
        description="valid|invalid|expired|lookup_failed|skipped|tavily_verified|unknown"
    )
    business_name: str | None = None
    expiry: str | None = None
    verify_url: str
    tavily_used: bool = False


class FindingSchema(BaseModel):
    """One observation from the grocery static analyzer."""
    code: str
    severity: Literal["info", "warning", "error"]
    message: str
    evidence: str | None = None


class NutritionSchema(BaseModel):
    """Per-100g nutrition values extracted by Gemini Vision."""
    calories_kcal: float | None = None
    protein_g: float | None = None
    total_fat_g: float | None = None
    saturated_fat_g: float | None = None
    carbohydrates_g: float | None = None
    sugar_g: float | None = None
    dietary_fiber_g: float | None = None
    sodium_mg: float | None = None


class ProductExtractionSchema(BaseModel):
    """
    Structured product data extracted directly from the image by Gemini Vision.

    Complements the rule-based GroceryAnalysis — provides ingredients list,
    nutrition table, diet flags, and brand identity that regex cannot reliably
    extract from free-form OCR text.
    """
    brand_name: str | None = None
    product_name: str | None = None
    product_type: str | None = None
    ingredients: list[str] = Field(default_factory=list)
    ingredients_count: int | None = None
    nutrition: NutritionSchema = Field(default_factory=NutritionSchema)
    serving_size: str | None = None
    servings_per_pack: float | None = None
    positives: list[str] = Field(
        default_factory=list,
        description="Genuinely good attributes the model identified (e.g. 'high fiber')",
    )
    negatives: list[str] = Field(
        default_factory=list,
        description="Health concerns identified (e.g. 'high sugar 15g/100g')",
    )
    allergens_declared: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    manufacturer: str | None = None
    net_weight: str | None = None
    serving_size_label: str | None = None
    is_vegetarian: bool | None = None
    is_vegan: bool | None = None
    is_gluten_free: bool | None = None
    contains_added_sugar: bool | None = None
    contains_preservatives: bool | None = None
    contains_artificial_colours: bool | None = None
    e_codes_found: list[str] = Field(default_factory=list)
    extraction_method: str = Field(
        description="gemini | openai_compat | failed — which provider succeeded",
    )


class GroceryScanResponse(BaseModel):
    """Response for POST /v1/grocery/scan."""
    scan_type: Literal["grocery"] = "grocery"

    risk_band: Literal["low", "medium", "high", "unknown"]
    expiry_status: Literal["SAFE", "NEAR_EXPIRY", "EXPIRED", "UNKNOWN"]

    # Phase 4: Trust Score
    trust_score: int | None = Field(
        None,
        description="0-100 deterministic trust score. None if context insufficient.",
    )
    trust_label: str | None = Field(
        None,
        description="EXCELLENT / GOOD / MODERATE / POOR / VERY POOR",
    )
    trust_reasons: list[str] = Field(
        default_factory=list,
        description="Human-readable reasons behind the trust score.",
    )

    # Phase 4: Community reports
    community_report_count: int = Field(
        0,
        description="Number of community reports for this product.",
    )
    community_flagged: bool = Field(
        False,
        description="True if ≥5 community reports have been filed.",
    )

    dates: dict[str, str] = Field(
        default_factory=dict,
        description="Extracted date snippets keyed by kind: mfg, exp, best_before, use_by",
    )
    findings: list[FindingSchema] = Field(default_factory=list)
    fssai: FssaiVerifySchema | None = None
    ingredients_count: int | None = None
    ingredients: list[str] = Field(
        default_factory=list,
        description="Full ingredients list extracted by Gemini Vision",
    )
    allergen_warnings: list[str] = Field(
        default_factory=list,
        description="Allergen names that triggered a user-profile match",
    )
    storage_warnings: list[StorageWarningSchema] = Field(default_factory=list)
    product_extraction: ProductExtractionSchema | None = Field(
        default=None,
        description="Rich structured data extracted by Gemini Vision (brand, nutrition, diet flags)",
    )
    barcode_data: str | None = None
    notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Unified scan schema (auto-classified)
# ---------------------------------------------------------------------------

class UnifiedScanResponse(BaseModel):
    """
    Response for POST /v1/scan/unified — auto-classifies the input and runs
    the appropriate pipeline.

    Exactly one of ``prescription``, ``medicine``, ``grocery`` is populated.
    The top-level ``scan_type``, ``verdict``, and ``expiry_status`` fields
    provide a quick summary without requiring clients to dig into the subtype.
    """
    scan_type: str = Field(description="prescription|medicine|grocery|unknown")
    category: str = Field(description="pharma|grocery|unknown — from classifier")
    scan_event_id: str | None = None

    # Summary fields — mirrors the active sub-response for quick client access
    verdict: Literal["VERIFIED", "SUSPICIOUS", "EXPIRED", "UNKNOWN"] | None = None
    verdict_score: float | None = None
    expiry_status: Literal["SAFE", "NEAR_EXPIRY", "EXPIRED", "UNKNOWN"] | None = None
    storage_warnings: list[StorageWarningSchema] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    # Typed sub-responses — at most one is non-None
    prescription: PrescriptionScanResponse | None = None
    medicine: MedicineScanResponse | None = None
    grocery: GroceryScanResponse | None = None
