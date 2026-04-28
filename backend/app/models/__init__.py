"""
Model registry — import every ORM model so that:
  1. Alembic's ``target_metadata`` in ``alembic/env.py`` sees the full table set.
  2. Relationship back-references resolve without circular import errors.
  3. A single ``from app.models import *`` in tests gives access to everything.

Import order matters for forward references — enums first, then base entities,
then satellite tables that reference them.
"""

from app.models.enums import (  # noqa: F401
    AllergenCategoryEnum,
    AuthenticityVerdictEnum,
    BloodGroupEnum,
    CertificationAuthorityEnum,
    DietaryPreferenceEnum,
    DosageFormEnum,
    GenderEnum,
    IntakeFrequencyEnum,
    InteractionSeverityEnum,
    ProductTypeEnum,
    ReactionSeverityEnum,
)

# Base must be imported after enums so the declarative registry is ready
from app.db.base import Base  # noqa: F401

# Core domain models
from app.models.user import User, UserAllergy, UserMedicalCondition  # noqa: F401
from app.models.health_profile import UserHealthProfile  # noqa: F401
from app.models.medicine import (  # noqa: F401
    DrugInteraction,
    Medicine,
    MedicineBatch,
    MedicineSalt,
    Salt,
    UserDrugReaction,
)
from app.models.grocery import GroceryIngredient, GroceryItem  # noqa: F401
from app.models.certification import ProductCertification  # noqa: F401
from app.models.prescription import Prescription, PrescriptionItem  # noqa: F401
from app.models.scan_event import MedicineScanEvent  # noqa: F401

__all__ = [
    "Base",
    # Enums
    "AllergenCategoryEnum",
    "AuthenticityVerdictEnum",
    "BloodGroupEnum",
    "CertificationAuthorityEnum",
    "DietaryPreferenceEnum",
    "DosageFormEnum",
    "GenderEnum",
    "IntakeFrequencyEnum",
    "InteractionSeverityEnum",
    "ProductTypeEnum",
    "ReactionSeverityEnum",
    # Models
    "User",
    "UserAllergy",
    "UserMedicalCondition",
    "UserHealthProfile",
    "Salt",
    "Medicine",
    "MedicineSalt",
    "MedicineBatch",
    "DrugInteraction",
    "UserDrugReaction",
    "GroceryItem",
    "GroceryIngredient",
    "ProductCertification",
    "Prescription",
    "PrescriptionItem",
    "MedicineScanEvent",
]
