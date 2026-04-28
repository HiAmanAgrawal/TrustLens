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


class GroceryScanResponse(BaseModel):
    """Response for POST /v1/grocery/scan."""
    scan_type: Literal["grocery"] = "grocery"

    risk_band: Literal["low", "medium", "high", "unknown"]
    expiry_status: Literal["SAFE", "NEAR_EXPIRY", "EXPIRED", "UNKNOWN"]

    dates: dict[str, str] = Field(
        default_factory=dict,
        description="Extracted date snippets keyed by kind: mfg, exp, best_before, use_by",
    )
    findings: list[FindingSchema] = Field(default_factory=list)
    fssai: FssaiVerifySchema | None = None
    ingredients_count: int | None = None
    allergen_warnings: list[str] = Field(
        default_factory=list,
        description="Allergen names that triggered a user-profile match",
    )
    storage_warnings: list[StorageWarningSchema] = Field(default_factory=list)
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
