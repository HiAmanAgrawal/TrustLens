"""
Drug Reaction (Side-Effect Memory) API.

Endpoints:
  POST /v1/users/{user_id}/reactions         — report a drug reaction
  GET  /v1/users/{user_id}/reactions         — list user's reactions
  GET  /v1/users/{user_id}/reactions/check/{medicine_id} — check a medicine
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DBSession
from app.models.enums import ReactionSeverityEnum
from app.services.side_effect_service import (
    ReactionWarning,
    check_medicine_for_reactions,
    get_user_reactions,
    report_reaction,
)

router = APIRouter()


class ReactionCreateRequest(BaseModel):
    salt_id:              uuid.UUID
    reaction_description: str = Field(..., max_length=500)
    severity:             ReactionSeverityEnum = ReactionSeverityEnum.MILD


class ReactionResponse(BaseModel):
    id:                   uuid.UUID
    user_id:              uuid.UUID
    salt_id:              uuid.UUID
    salt_name:            str | None
    reaction_description: str | None
    severity:             str
    created_at:           object  # datetime — serialised as ISO string

    model_config = {"from_attributes": True}


class ReactionWarningResponse(BaseModel):
    salt_name:            str
    reaction_description: str
    severity:             str


@router.post("/{user_id}/reactions", status_code=201)
async def report_drug_reaction(
    user_id: uuid.UUID,
    body:    ReactionCreateRequest,
    db:      DBSession,
):
    """Record that a user experienced a reaction to a specific drug salt."""
    rxn = await report_reaction(
        db,
        user_id=user_id,
        salt_id=body.salt_id,
        reaction_description=body.reaction_description,
        severity=body.severity,
    )
    await db.commit()
    return {
        "id":                   str(rxn.id),
        "user_id":              str(rxn.user_id),
        "salt_id":              str(rxn.salt_id),
        "reaction_description": rxn.reaction_description,
        "severity":             rxn.severity.value if rxn.severity else None,
    }


@router.get("/{user_id}/reactions")
async def list_drug_reactions(
    user_id: uuid.UUID,
    db:      DBSession,
):
    """Return all drug reactions the user has reported, newest first."""
    reactions = await get_user_reactions(db, user_id)
    return [
        {
            "id":                   str(r.id),
            "salt_id":              str(r.salt_id),
            "salt_name":            r.salt.name if r.salt else None,
            "reaction_description": r.reaction_description,
            "severity":             r.severity.value if r.severity else None,
            "created_at":           r.created_at.isoformat() if r.created_at else None,
        }
        for r in reactions
    ]


@router.get("/{user_id}/reactions/check/{medicine_id}", response_model=list[ReactionWarningResponse])
async def check_medicine_reactions(
    user_id:     uuid.UUID,
    medicine_id: uuid.UUID,
    db:          DBSession,
):
    """
    Cross-reference a medicine's salt composition against the user's
    personal side-effect history. Returns warnings if any salts overlap.
    """
    warnings: list[ReactionWarning] = await check_medicine_for_reactions(
        db, medicine_id=medicine_id, user_id=user_id,
    )
    return [
        ReactionWarningResponse(
            salt_name=w.salt_name,
            reaction_description=w.reaction_description,
            severity=w.severity,
        )
        for w in warnings
    ]
