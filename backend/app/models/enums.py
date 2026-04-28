"""
Centralised Python enumerations for every domain concept in TrustLens.

WHY centralised:
  - Alembic generates each enum as a native PostgreSQL ENUM type only once.
  - Pydantic schemas import from here so the Python values always match the DB.
  - Adding a new variant in one place updates every layer simultaneously.

NAMING CONVENTION: StrEnum (inherits str) so serialisation is transparent —
  ``json.dumps(AuthenticityVerdictEnum.VERIFIED)`` → ``"VERIFIED"``.
"""

from __future__ import annotations

import enum


class GenderEnum(str, enum.Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"
    PREFER_NOT_TO_SAY = "prefer_not_to_say"


class DietaryPreferenceEnum(str, enum.Enum):
    VEGETARIAN = "vegetarian"
    VEGAN = "vegan"
    NON_VEGETARIAN = "non_vegetarian"
    JAIN = "jain"                   # No root vegetables
    HALAL = "halal"
    KOSHER = "kosher"
    GLUTEN_FREE = "gluten_free"


class DosageFormEnum(str, enum.Enum):
    TABLET = "tablet"
    CAPSULE = "capsule"
    SYRUP = "syrup"
    INJECTION = "injection"
    CREAM = "cream"
    DROPS = "drops"
    POWDER = "powder"
    PATCH = "patch"
    INHALER = "inhaler"
    SUPPOSITORY = "suppository"
    GEL = "gel"
    LOTION = "lotion"
    OINTMENT = "ointment"
    SUSPENSION = "suspension"
    LOZENGE = "lozenge"


class AuthenticityVerdictEnum(str, enum.Enum):
    """
    Result of a medicine batch scan against official data sources (CDSCO / scraper).

    VERIFIED        – Barcode, batch number, expiry, and manufacturer all match.
    SUSPICIOUS      – At least one field mismatches or the product isn't in the DB;
                      possible counterfeit or data gap — show a caution banner, not an alert.
    EXPIRED         – The batch's expiry_date has passed; authentic but unsafe.
    UNKNOWN         – Could not retrieve enough data to reach any verdict.
    """
    VERIFIED = "VERIFIED"
    SUSPICIOUS = "SUSPICIOUS"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


class CertificationAuthorityEnum(str, enum.Enum):
    """Issuing bodies whose certifications we track on products."""
    FSSAI = "FSSAI"          # Food Safety and Standards Authority of India
    CDSCO = "CDSCO"          # Central Drugs Standard Control Organisation
    ISO = "ISO"
    AYUSH = "AYUSH"          # Ministry of Ayurveda/Yoga/Unani/Siddha/Homeopathy
    BIS = "BIS"              # Bureau of Indian Standards
    ORGANIC_INDIA = "ORGANIC_INDIA"
    VEGAN_SOCIETY = "VEGAN_SOCIETY"


class ProductTypeEnum(str, enum.Enum):
    """
    Discriminator column for the polymorphic product_certifications table.
    Using a column instead of separate FK columns avoids a migration every time
    a new product domain is added.
    """
    MEDICINE = "medicine"
    GROCERY = "grocery"


class InteractionSeverityEnum(str, enum.Enum):
    """
    Standard pharmacovigilance tiers used by DrugBank / openFDA.

    CONTRAINDICATED is an absolute bar — the UI must always block the combination
    regardless of user preferences or dosage.
    """
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"
    CONTRAINDICATED = "contraindicated"


class IntakeFrequencyEnum(str, enum.Enum):
    ONCE_DAILY = "once_daily"
    TWICE_DAILY = "twice_daily"
    THRICE_DAILY = "thrice_daily"
    FOUR_TIMES_DAILY = "four_times_daily"
    AS_NEEDED = "as_needed"          # PRN dosing
    WEEKLY = "weekly"
    EVERY_OTHER_DAY = "every_other_day"
    BEFORE_FOOD = "before_food"
    AFTER_FOOD = "after_food"
    WITH_FOOD = "with_food"


class ReactionSeverityEnum(str, enum.Enum):
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"
    LIFE_THREATENING = "life_threatening"


class AllergenCategoryEnum(str, enum.Enum):
    """
    Top-14 EU allergens (Regulation EU 1169/2011) + common Indian additions.

    Stored as a category so ingredient matching uses enum equality instead of
    fragile substring comparison on raw ingredient strings.
    """
    GLUTEN = "gluten"
    CRUSTACEANS = "crustaceans"
    EGGS = "eggs"
    FISH = "fish"
    PEANUTS = "peanuts"
    SOYBEANS = "soybeans"
    MILK = "milk"
    TREE_NUTS = "tree_nuts"      # cashews, almonds, walnuts, etc.
    CELERY = "celery"
    MUSTARD = "mustard"
    SESAME = "sesame"
    SULPHITES = "sulphites"
    LUPIN = "lupin"
    MOLLUSCS = "molluscs"
    # Indian-specific additions
    COCONUT = "coconut"
    CORN = "corn"
    LATEX = "latex"
    OTHER = "other"


class BloodGroupEnum(str, enum.Enum):
    A_POSITIVE = "A+"
    A_NEGATIVE = "A-"
    B_POSITIVE = "B+"
    B_NEGATIVE = "B-"
    AB_POSITIVE = "AB+"
    AB_NEGATIVE = "AB-"
    O_POSITIVE = "O+"
    O_NEGATIVE = "O-"
    UNKNOWN = "unknown"


class MessageDirectionEnum(str, enum.Enum):
    INBOUND = "inbound"   # message from the user
    OUTBOUND = "outbound" # message from TrustLens


class MessageTypeEnum(str, enum.Enum):
    # Values match the PostgreSQL enum created by the initial migration (uppercase).
    TEXT = "TEXT"
    IMAGE = "IMAGE"
    AUDIO = "AUDIO"
    DOCUMENT = "DOCUMENT"
    STICKER = "STICKER"


class OnboardingStepEnum(str, enum.Enum):
    """
    State machine steps for the WhatsApp onboarding flow.

    AWAITING_* states mean we sent a question and are waiting for the user's answer.
    COMPLETE means all info collected and the user row has been persisted to DB.
    ACTIVE is set for fully-onboarded users in normal conversation mode.
    """
    AWAITING_NAME = "awaiting_name"
    AWAITING_DIET = "awaiting_diet"
    AWAITING_ALLERGIES = "awaiting_allergies"
    AWAITING_MEDICINES = "awaiting_medicines"
    COMPLETE = "complete"
    ACTIVE = "active"
