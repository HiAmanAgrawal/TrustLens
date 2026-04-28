"""phase3_scan_type_column

Revision ID: 4187424ae0cf
Revises: e35c3942a989
Create Date: 2026-04-28 23:46:31.899925
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# pgvector type — stored as Text placeholder; app patches to Vector(1536) at runtime.
_EMBEDDING_TYPE = sa.Text()

# revision identifiers, used by Alembic.
revision: str = '4187424ae0cf'
down_revision: str | None = 'e35c3942a989'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # name_embedding columns stay as Text — the app patches them to Vector at runtime.
    # Only apply the scan_type column and barcode index changes.

    # Drop and recreate the grocery_items barcode index (was non-unique, now unique in model)
    op.drop_index(op.f('ix_grocery_items_barcode'), table_name='grocery_items')
    op.create_index(
        op.f('ix_grocery_items_barcode'), 'grocery_items', ['barcode'], unique=True
    )

    # Phase 3: add scan_type column to medicine_scan_events
    op.add_column(
        'medicine_scan_events',
        sa.Column('scan_type', sa.String(length=20), nullable=True),
    )
    op.create_index(
        op.f('ix_medicine_scan_events_scan_type'),
        'medicine_scan_events',
        ['scan_type'],
        unique=False,
    )

    # medicines barcode index direction changed in the model — re-create as non-unique
    op.drop_index(op.f('ix_medicines_barcode'), table_name='medicines')
    op.create_index('ix_medicines_barcode', 'medicines', ['barcode'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_medicines_barcode', table_name='medicines')
    op.create_index(op.f('ix_medicines_barcode'), 'medicines', ['barcode'], unique=True)
    op.drop_index(
        op.f('ix_medicine_scan_events_scan_type'), table_name='medicine_scan_events'
    )
    op.drop_column('medicine_scan_events', 'scan_type')
    op.drop_index(op.f('ix_grocery_items_barcode'), table_name='grocery_items')
    op.create_index(
        op.f('ix_grocery_items_barcode'), 'grocery_items', ['barcode'], unique=False
    )
