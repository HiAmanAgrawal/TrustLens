"""
Trust Score Engine — deterministic, rule-based 0-100 scorer for scanned products.

WHY deterministic (not LLM-based):
  Trust scores are safety-adjacent. Users make purchase decisions on them.
  A deterministic engine gives auditable, reproducible results with clear
  deduction/bonus reasons — no hallucinated scores, no black-box AI.

SCORE BANDS:
  ≥ 80  EXCELLENT  — high confidence, verified
  ≥ 65  GOOD       — mostly verified, minor gaps
  ≥ 50  MODERATE   — proceed with caution
  ≥ 35  POOR       — significant concerns found
  <  35  VERY POOR  — serious red flags, avoid

INPUT: flat product context dict (same schema as product_context.py output)
       + optional user profile dict for personalised deductions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ── Thresholds (ICMR-NIN / WHO / FSSAI guidelines) ─────────────────────────
_SUGAR_HIGH_G    = 10.0   # g per 100g
_SODIUM_HIGH_MG  = 400.0  # mg per 100g
_SATFAT_HIGH_G   = 5.0    # g per 100g
_CALORIES_HIGH   = 400.0  # kcal per 100g

# Community report count that triggers a major deduction.
_COMMUNITY_FLAG_THRESHOLD = 5


@dataclass
class TrustScoreResult:
    score: int
    label: str
    reasons: list[str]             = field(default_factory=list)
    deductions: list[tuple[str, int]] = field(default_factory=list)
    bonuses: list[tuple[str, int]]    = field(default_factory=list)
    disclaimer: str = (
        "⚕️ Trust score is informational only. "
        "Consult a doctor or dietitian for medical decisions."
    )


def _label(score: int) -> str:
    if score >= 80: return "EXCELLENT"
    if score >= 65: return "GOOD"
    if score >= 50: return "MODERATE"
    if score >= 35: return "POOR"
    return "VERY POOR"


def compute_trust_score(
    product_context: dict,
    user_profile: dict | None = None,
    community_report_count: int = 0,
) -> TrustScoreResult:
    """
    Compute a deterministic 0-100 trust score from a flat product context dict.

    Args:
        product_context:       Dict from product_context.py (grocery or medicine).
        user_profile:          Optional dict with 'allergens', 'dietary_preference',
                               'conditions' for personalised deductions.
        community_report_count: Pre-fetched count of community reports for this
                               product/batch — avoids a DB call inside this pure fn.
    """
    ctx = product_context
    scan_type = ctx.get("scan_type", "grocery")

    bonuses: list[tuple[str, int]]    = []
    deductions: list[tuple[str, int]] = []
    reasons: list[str]                = []

    logger.debug(
        "trust_score.compute | scan_type=%r brand=%r",
        scan_type, ctx.get("brand_name"),
    )

    # ── 1. FSSAI (grocery) / Verdict (medicine) ─────────────────────────────
    if scan_type == "grocery":
        fssai = ctx.get("fssai") or {}
        online_status = (fssai.get("online_status") or "").lower()
        fmt_valid = fssai.get("format_valid")

        if online_status == "valid":
            bonuses.append(("FSSAI license verified online", 20))
        elif online_status == "invalid":
            deductions.append(("FSSAI license invalid or revoked", 15))
            reasons.append("FSSAI status is invalid — product may not be authorised for sale.")
        elif fmt_valid:
            bonuses.append(("FSSAI license format valid (online check pending)", 8))
        else:
            deductions.append(("FSSAI license missing or unreadable", 10))
            reasons.append("No valid FSSAI license found on this product.")

    else:  # medicine
        verdict = (ctx.get("verdict") or "UNKNOWN").upper()
        if verdict == "VERIFIED":
            bonuses.append(("Medicine batch verified by official data", 25))
        elif verdict == "SUSPICIOUS":
            deductions.append(("Medicine batch flagged as suspicious", 20))
            reasons.append("This batch could not be fully verified against official records.")
        elif verdict == "EXPIRED":
            deductions.append(("Medicine is expired", 30))
            reasons.append("This medicine has passed its expiry date — do not consume.")

    # ── 2. Expiry status ─────────────────────────────────────────────────────
    expiry = (ctx.get("expiry_status") or "UNKNOWN").upper()
    if expiry == "SAFE":
        bonuses.append(("Expiry date valid", 5))
    elif expiry == "NEAR_EXPIRY":
        deductions.append(("Expiry within 30 days", 5))
        reasons.append("Product expires within 30 days — consume promptly or avoid.")
    elif expiry == "EXPIRED":
        deductions.append(("Product is expired", 20))
        reasons.append("This product has passed its expiry date.")

    # ── 3. Ingredients transparency ─────────────────────────────────────────
    ingredients = ctx.get("ingredients") or []
    ing_count   = ctx.get("ingredients_count") or len(ingredients)
    if ing_count and ing_count > 0:
        bonuses.append(("Ingredients list readable", 10))
    else:
        deductions.append(("Ingredients list not readable", 5))
        reasons.append("Could not read full ingredients list from label.")

    # ── 4. Certifications ────────────────────────────────────────────────────
    certs = ctx.get("certifications") or []
    cert_bonus = min(len(certs) * 5, 15)
    if cert_bonus:
        bonuses.append((f"{len(certs)} certification(s) found", cert_bonus))

    # ── 5. Nutrition concerns (grocery only) ────────────────────────────────
    if scan_type == "grocery":
        nutrition = ctx.get("nutrition_per_100g") or {}
        sugar_g   = nutrition.get("sugar_g")
        sodium_mg = nutrition.get("sodium_mg")
        satfat_g  = nutrition.get("saturated_fat_g")
        cal_kcal  = nutrition.get("calories_kcal")
        fiber_g   = nutrition.get("dietary_fiber_g")
        protein_g = nutrition.get("protein_g")

        if sugar_g is not None and sugar_g > _SUGAR_HIGH_G:
            deductions.append((f"High sugar ({sugar_g}g / 100g)", 5))
            reasons.append(f"Contains {sugar_g}g sugar per 100g — above the 10g recommended limit.")
        if sodium_mg is not None and sodium_mg > _SODIUM_HIGH_MG:
            deductions.append((f"High sodium ({sodium_mg}mg / 100g)", 5))
            reasons.append(f"Contains {sodium_mg}mg sodium per 100g — above 400mg guideline.")
        if satfat_g is not None and satfat_g > _SATFAT_HIGH_G:
            deductions.append((f"High saturated fat ({satfat_g}g / 100g)", 3))
            reasons.append(f"High saturated fat content ({satfat_g}g per 100g).")
        if cal_kcal is not None and cal_kcal > _CALORIES_HIGH:
            deductions.append((f"High calorie density ({cal_kcal} kcal / 100g)", 3))

        # Positives
        if fiber_g is not None and fiber_g >= 3:
            bonuses.append((f"Good dietary fiber ({fiber_g}g / 100g)", 3))
        if protein_g is not None and protein_g >= 5:
            bonuses.append((f"Good protein content ({protein_g}g / 100g)", 3))

        # E-codes / additives
        e_codes = ctx.get("e_codes_found") or []
        if e_codes:
            e_deduction = min(len(e_codes) * 3, 12)
            deductions.append((f"{len(e_codes)} E-code additive(s) found", e_deduction))

    # ── 6. Personalised deductions (user profile) ───────────────────────────
    if user_profile:
        allergen_warnings = ctx.get("allergen_warnings") or []
        if allergen_warnings:
            deductions.append((f"Allergen conflict: {', '.join(allergen_warnings[:3])}", 25))
            reasons.append(
                f"⚠️ ALLERGEN WARNING: Contains allergens you are sensitive to: "
                f"{', '.join(allergen_warnings)}."
            )

        diet = user_profile.get("dietary_preference") or ""
        if diet and scan_type == "grocery":
            is_veg  = ctx.get("is_vegetarian")
            is_vegan = ctx.get("is_vegan")
            if diet in ("vegetarian", "jain") and is_veg is False:
                deductions.append(("Diet mismatch: product is non-vegetarian", 15))
                reasons.append("This product contains non-vegetarian ingredients — conflicts with your dietary preference.")
            elif diet == "vegan" and is_vegan is False:
                deductions.append(("Diet mismatch: product is not vegan", 15))
                reasons.append("This product is not suitable for vegans.")
            elif diet == "gluten_free" and ctx.get("is_gluten_free") is False:
                deductions.append(("Diet mismatch: product contains gluten", 15))
                reasons.append("This product contains gluten — conflicts with your gluten-free preference.")

    # ── 7. Community reports ─────────────────────────────────────────────────
    if community_report_count >= _COMMUNITY_FLAG_THRESHOLD:
        deductions.append((f"Community flagged ({community_report_count} reports)", 20))
        reasons.append(
            f"⚠️ {community_report_count} users have reported issues with this product/batch. "
            "Proceed with caution."
        )
    elif community_report_count > 0:
        reasons.append(
            f"ℹ️ {community_report_count} user(s) have reported minor concerns about this product."
        )

    # ── 8. Risk band cap ────────────────────────────────────────────────────
    risk_band = (ctx.get("risk_band") or "unknown").lower()

    # ── Compute raw score ────────────────────────────────────────────────────
    raw = 55  # neutral starting point
    for _, pts in bonuses:
        raw += pts
    for _, pts in deductions:
        raw -= pts

    # Apply risk band caps (a HIGH risk product cannot score above 40)
    caps = {"high": 40, "medium": 70}
    if risk_band in caps:
        raw = min(raw, caps[risk_band])

    score = max(0, min(100, raw))

    logger.info(
        "trust_score.result | brand=%r score=%d label=%s bonuses=%d deductions=%d",
        ctx.get("brand_name"), score, _label(score), len(bonuses), len(deductions),
    )

    return TrustScoreResult(
        score=score,
        label=_label(score),
        reasons=reasons,
        bonuses=bonuses,
        deductions=deductions,
    )
