"""
UserService — CRUD + lookup operations for users and their health sub-records.

Every method is a standalone async function that receives a session rather than
storing it as instance state. This keeps services stateless and easy to compose
inside LangGraph agent nodes (which are plain async functions, not classes).

WHY services exist between routes and the ORM:
  - Routes own HTTP concerns (status codes, request parsing).
  - Services own business logic (existence checks, default creation, de-duplication).
  - Splitting them means the same logic is callable from the WhatsApp webhook,
    the REST API, and agent tools without duplicating code.
"""

from __future__ import annotations

import logging
import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import (
    ConflictError,
    UserNotFoundError,
)
from app.models.user import User, UserAllergy, UserMedicalCondition
from app.schemas.user import (
    UserAllergyCreate,
    UserCreate,
    UserMedicalConditionCreate,
    UserUpdate,
)

logger = logging.getLogger(__name__)


async def create_user(session: AsyncSession, data: UserCreate) -> User:
    """
    Create a new user.

    Raises ConflictError if a user with the same phone, email, or WhatsApp ID
    already exists — checked before insert to surface a clean 409 rather than
    a Postgres constraint violation.
    """
    logger.info(
        "user_service.create | name=%r phone=%r email=%r",
        data.full_name, data.phone_number, data.email,
    )
    await _assert_no_duplicate_contact(session, data)

    user = User(
        full_name=data.full_name,
        phone_number=data.phone_number,
        email=data.email,
        whatsapp_user_id=data.whatsapp_user_id,
        dob=data.dob,
        gender=data.gender,
    )
    session.add(user)
    await session.flush()   # flush to get the PK without committing
    logger.info("user_service.created | user_id=%s", user.id)
    return user


async def get_user_by_id(
    session: AsyncSession, user_id: uuid.UUID, *, with_profile: bool = False
) -> User:
    """
    Fetch a user by primary key. Raises UserNotFoundError if not found.

    ``with_profile=True`` eagerly loads allergies, conditions, and health_profile
    in a single query to avoid N+1 round-trips.
    """
    logger.debug("user_service.get_by_id | user_id=%s with_profile=%s", user_id, with_profile)

    stmt = sa.select(User).where(User.id == user_id)
    if with_profile:
        stmt = stmt.options(
            selectinload(User.health_profile),
            selectinload(User.allergies),
            selectinload(User.medical_conditions),
        )

    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        logger.warning("user_service.not_found | user_id=%s", user_id)
        raise UserNotFoundError(str(user_id))
    return user


async def get_user_by_whatsapp_id(
    session: AsyncSession, whatsapp_user_id: str
) -> User | None:
    """Return the user for a given WhatsApp sender ID, or None if not registered."""
    logger.debug("user_service.get_by_wa_id | wa_id=%r", whatsapp_user_id)
    result = await session.execute(
        sa.select(User).where(User.whatsapp_user_id == whatsapp_user_id)
    )
    return result.scalar_one_or_none()


async def update_user(
    session: AsyncSession, user_id: uuid.UUID, data: UserUpdate
) -> User:
    """Apply partial updates to a user. Only non-None fields are changed."""
    user = await get_user_by_id(session, user_id)
    changes = data.model_dump(exclude_none=True)
    if not changes:
        logger.debug("user_service.update | no changes for user_id=%s", user_id)
        return user

    for field, value in changes.items():
        setattr(user, field, value)

    await session.flush()
    logger.info("user_service.updated | user_id=%s fields=%s", user_id, list(changes))
    return user


async def deactivate_user(session: AsyncSession, user_id: uuid.UUID) -> User:
    """Soft-delete: set is_active=False rather than dropping the row."""
    user = await get_user_by_id(session, user_id)
    user.is_active = False
    await session.flush()
    logger.info("user_service.deactivated | user_id=%s", user_id)
    return user


# ---------------------------------------------------------------------------
# Allergies
# ---------------------------------------------------------------------------

async def add_allergy(
    session: AsyncSession, user_id: uuid.UUID, data: UserAllergyCreate
) -> UserAllergy:
    """Add an allergen to the user's profile. Raises ConflictError on duplicate."""
    logger.info(
        "user_service.add_allergy | user_id=%s allergen=%r", user_id, data.allergen
    )
    existing = await session.execute(
        sa.select(UserAllergy).where(
            UserAllergy.user_id == user_id,
            UserAllergy.allergen == data.allergen,
        )
    )
    if existing.scalar_one_or_none():
        raise ConflictError(f"Allergen '{data.allergen}' is already on this user's profile.")

    allergy = UserAllergy(
        user_id=user_id,
        allergen=data.allergen,
        allergen_category=data.allergen_category,
        severity_note=data.severity_note,
    )
    session.add(allergy)
    await session.flush()
    logger.info("user_service.allergy_added | allergy_id=%s", allergy.id)
    return allergy


async def remove_allergy(
    session: AsyncSession, user_id: uuid.UUID, allergy_id: uuid.UUID
) -> None:
    """Remove an allergen record. Raises NotFoundError if not found."""
    from app.core.exceptions import NotFoundError
    result = await session.execute(
        sa.select(UserAllergy).where(
            UserAllergy.id == allergy_id,
            UserAllergy.user_id == user_id,
        )
    )
    allergy = result.scalar_one_or_none()
    if not allergy:
        raise NotFoundError(f"Allergy '{allergy_id}' not found for this user.")

    await session.delete(allergy)
    await session.flush()
    logger.info("user_service.allergy_removed | allergy_id=%s", allergy_id)


async def list_allergies(
    session: AsyncSession, user_id: uuid.UUID
) -> list[UserAllergy]:
    """Return all allergens for a user."""
    result = await session.execute(
        sa.select(UserAllergy)
        .where(UserAllergy.user_id == user_id)
        .order_by(UserAllergy.allergen)
    )
    return list(result.scalars())


# ---------------------------------------------------------------------------
# Medical conditions
# ---------------------------------------------------------------------------

async def add_medical_condition(
    session: AsyncSession, user_id: uuid.UUID, data: UserMedicalConditionCreate
) -> UserMedicalCondition:
    logger.info(
        "user_service.add_condition | user_id=%s condition=%r",
        user_id, data.condition_name,
    )
    condition = UserMedicalCondition(
        user_id=user_id,
        condition_name=data.condition_name,
        icd_10_code=data.icd_10_code,
        diagnosed_at=data.diagnosed_at,
        is_active=data.is_active,
        notes=data.notes,
    )
    session.add(condition)
    await session.flush()
    return condition


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _assert_no_duplicate_contact(session: AsyncSession, data: UserCreate) -> None:
    """Raise ConflictError if any contact field is already registered."""
    clauses: list[sa.ColumnElement] = []
    if data.phone_number:
        clauses.append(User.phone_number == data.phone_number)
    if data.email:
        clauses.append(User.email == data.email)
    if data.whatsapp_user_id:
        clauses.append(User.whatsapp_user_id == data.whatsapp_user_id)

    if not clauses:
        return

    stmt = sa.select(User).where(sa.or_(*clauses))
    result = await session.execute(stmt)
    if result.scalar_one_or_none():
        from app.core.exceptions import DuplicateUserError
        raise DuplicateUserError()
