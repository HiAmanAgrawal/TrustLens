"""add community_reports and refill_reminders

Revision ID: 9747c3fbc1c5
Revises: 4187424ae0cf
Create Date: 2026-04-29 02:04:14.258922
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '9747c3fbc1c5'
down_revision: str | None = '4187424ae0cf'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'community_reports',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column('product_id', sa.UUID(), nullable=False),
        sa.Column(
            'product_type',
            sa.Enum('MEDICINE', 'GROCERY', name='producttypeenum'),
            nullable=False,
        ),
        sa.Column('batch_id', sa.UUID(), nullable=True),
        sa.Column(
            'report_type',
            sa.Enum(
                'SUSPICIOUS_LABEL', 'ADVERSE_REACTION', 'COUNTERFEIT',
                'QUALITY_ISSUE', 'EXPIRED_SOLD', 'WRONG_PRODUCT',
                name='reporttypeenum',
            ),
            nullable=False,
        ),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_auto_flagged', sa.Boolean(), nullable=False),
        sa.Column('flag_count_at_time', sa.Integer(), nullable=True),
        sa.Column('is_verified', sa.Boolean(), nullable=False),
        sa.Column('verified_by', sa.UUID(), nullable=True),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['verified_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_community_reports_product_batch',
        'community_reports',
        ['product_id', 'product_type', 'batch_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_community_reports_product_id'),
        'community_reports',
        ['product_id'],
        unique=False,
    )
    op.create_index(
        'uq_community_report_user_product_batch',
        'community_reports',
        ['user_id', 'product_id', 'batch_id'],
        unique=True,
        postgresql_where='user_id IS NOT NULL',
    )

    op.create_table(
        'refill_reminders',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('medicine_id', sa.UUID(), nullable=False),
        sa.Column('prescription_item_id', sa.UUID(), nullable=True),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('quantity_prescribed', sa.Integer(), nullable=False),
        sa.Column(
            'frequency',
            sa.Enum(
                'ONCE_DAILY', 'TWICE_DAILY', 'THRICE_DAILY', 'FOUR_TIMES_DAILY',
                'AS_NEEDED', 'WEEKLY', 'EVERY_OTHER_DAY',
                'BEFORE_FOOD', 'AFTER_FOOD', 'WITH_FOOD',
                name='intakefrequencyenum',
            ),
            nullable=False,
        ),
        sa.Column('days_supply', sa.Integer(), nullable=False),
        sa.Column('finish_date', sa.Date(), nullable=False),
        sa.Column('reminder_date', sa.Date(), nullable=False),
        sa.Column('is_sent', sa.Boolean(), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['medicine_id'], ['medicines.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(
            ['prescription_item_id'], ['prescription_items.id'], ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_refill_reminders_due',
        'refill_reminders',
        ['reminder_date', 'is_sent'],
        unique=False,
    )
    op.create_index(
        'ix_refill_reminders_user',
        'refill_reminders',
        ['user_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_refill_reminders_user', table_name='refill_reminders')
    op.drop_index('ix_refill_reminders_due', table_name='refill_reminders')
    op.drop_table('refill_reminders')
    op.drop_index(
        'uq_community_report_user_product_batch',
        table_name='community_reports',
        postgresql_where='user_id IS NOT NULL',
    )
    op.drop_index(
        op.f('ix_community_reports_product_id'),
        table_name='community_reports',
    )
    op.drop_index('ix_community_reports_product_batch', table_name='community_reports')
    op.drop_table('community_reports')
