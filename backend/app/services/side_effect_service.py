"""
Side-Effect Memory — personal drug reaction history.

PROBLEM SOLVED:
  A user says "I got a rash from Crocin last week." We record the active
  salt (paracetamol). Next time they scan ANY paracetamol product — regardless
  of brand — we flag it automatically. This is a safety net that transcends
  brand-level awareness.

HOW IT WORKS:
  1. report_reaction() stores a UserDrugReaction row linked to a Salt.
  2. check_medicine_for_reactions() fetches the medicine's salt IDs and cross-
     references against all salts the user has reported reactions to.
  3. If overlap → return warning strings mentioning the specific salt + reaction.

WHY salt-level (not medicine-level):
  Brand drugs change. Generic substitutions happen. The chemical compound
  (salt) is the stable identifier. "Paracetamol caused me nausea" = any
  brand carrying paracetamol should show a caution banner.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.enums import ReactionSeverityEnum
from app.models.medicine import MedicineSalt, Salt, UserDrugReaction

logger = logging.getLogger(__name__)


@dataclass
class ReactionWarning:
    salt_name: str
    reaction_description: str
    severity: str


async def report_reaction(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    salt_id: uuid.UUID,
    reaction_description: str,
    severity: ReactionSeverityEnum = ReactionSeverityEnum.MILD,
) -> UserDrugReaction:
    """
    Record that a user experienced a reaction to a specific drug salt.

    Idempotent by design — if a reaction for the same (user, salt) already
    exists we update the description/severity rather than duplicating.
    """
    # Check for existing record
    stmt = select(UserDrugReaction).where(
        UserDrugReaction.user_id == user_id,
        UserDrugReaction.salt_id == salt_id,
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        existing.reaction_description = reaction_description
        existing.severity = severity
        logger.info(
            "side_effect.update | user_id=%s salt_id=%s severity=%s",
            user_id, salt_id, severity,
        )
        return existing

    reaction = UserDrugReaction(
        user_id=user_id,
        salt_id=salt_id,
        reaction_description=reaction_description,
        severity=severity,
    )
    session.add(reaction)
    await session.flush()
    logger.info(
        "side_effect.report | user_id=%s salt_id=%s severity=%s",
        user_id, salt_id, severity,
    )
    return reaction


async def get_user_reaction_salts(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> list[uuid.UUID]:
    """
    Return the salt IDs for all reactions the user has reported.

    Used by the scan pipeline to pre-load the user's reaction history
    before checking a newly scanned medicine.
    """
    stmt = select(UserDrugReaction.salt_id).where(
        UserDrugReaction.user_id == user_id,
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_user_reactions(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> list[UserDrugReaction]:
    """Return full UserDrugReaction objects with salt names loaded."""
    stmt = (
        select(UserDrugReaction)
        .options(selectinload(UserDrugReaction.salt))
        .where(UserDrugReaction.user_id == user_id)
        .order_by(UserDrugReaction.created_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def check_medicine_for_reactions(
    session: AsyncSession,
    medicine_id: uuid.UUID,
    user_id: uuid.UUID,
) -> list[ReactionWarning]:
    """
    Cross-reference a medicine's salt composition against the user's
    personal reaction history.

    Returns a list of warnings (one per overlapping salt), or empty list
    if no conflicts.
    """
    # Step 1: Get salt IDs for this medicine
    salt_stmt = (
        select(MedicineSalt)
        .options(selectinload(MedicineSalt.salt))
        .where(MedicineSalt.medicine_id == medicine_id)
    )
    result = await session.execute(salt_stmt)
    medicine_salts: list[MedicineSalt] = list(result.scalars().all())
    medicine_salt_ids = {ms.salt_id for ms in medicine_salts}

    if not medicine_salt_ids:
        return []

    # Step 2: Get user's reported reaction salts
    reaction_stmt = (
        select(UserDrugReaction)
        .options(selectinload(UserDrugReaction.salt))
        .where(
            UserDrugReaction.user_id == user_id,
            UserDrugReaction.salt_id.in_(medicine_salt_ids),
        )
    )
    result = await session.execute(reaction_stmt)
    reactions: list[UserDrugReaction] = list(result.scalars().all())

    warnings: list[ReactionWarning] = []
    for rxn in reactions:
        salt_name = rxn.salt.name if rxn.salt else str(rxn.salt_id)
        warnings.append(ReactionWarning(
            salt_name=salt_name,
            reaction_description=rxn.reaction_description or "Unspecified reaction",
            severity=rxn.severity.value if rxn.severity else "mild",
        ))
        logger.warning(
            "side_effect.scan_hit | user_id=%s salt=%r severity=%s",
            user_id, salt_name, rxn.severity,
        )

    return warnings
