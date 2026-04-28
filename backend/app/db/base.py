"""
SQLAlchemy declarative base and shared column type aliases.

WHY shared aliases (uuid_pk, created_at, updated_at):
  Every table needs the same UUID primary key and audit timestamps.
  Defining them once as Annotated types lets mapped_column pick up all kwargs
  without repeating primary_key=True, server_default=func.now(), etc. in
  every model — the DRY principle applied to schema definition.

IMPORTANT: Every model file must import ``Base`` from here so Alembic's
  ``target_metadata`` in ``alembic/env.py`` sees the complete table registry.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, mapped_column


# ---------------------------------------------------------------------------
# Reusable column type aliases
# ---------------------------------------------------------------------------

# UUID primary key with both a Python-side default (uuid4) and a DB-side
# server_default (gen_random_uuid) so inserts work whether or not the Python
# layer sets the value.
uuid_pk = Annotated[
    uuid.UUID,
    mapped_column(
        sa.UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    ),
]

# Timezone-aware created_at — set once on INSERT, never updated.
created_at_col = Annotated[
    datetime,
    mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        init=False,
    ),
]

# Timezone-aware updated_at — refreshed on every UPDATE via an SA event
# (see core/database.py) and a DB trigger is NOT needed because SA handles it.
updated_at_col = Annotated[
    datetime,
    mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
        init=False,
    ),
]


# ---------------------------------------------------------------------------
# Declarative base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    """
    All ORM models inherit from this.

    Inheriting a single Base lets Alembic's autogenerate detect all tables
    by inspecting ``Base.metadata`` — no manual table registration needed.
    """
    pass
