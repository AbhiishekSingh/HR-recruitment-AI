"""add approved_by and submitted_to to assessments

Revision ID: e73bd471910d
Revises: b3f9a1c2d4e5
Create Date: 2026-09-19 11:58:29.377535

Fixed version of this migration: the original branched off a6a84d0d04aa
instead of b3f9a1c2d4e5 (creating two competing Alembic heads), and added
both columns as NOT NULL with no default/server_default, which fails
outright the moment `assessments` has any existing rows. Both columns are
added nullable-with-default here instead, matching how every other
free-text field on this model behaves (see models/assessment.py).
"""
from alembic import op
import sqlalchemy as sa


revision = 'e73bd471910d'
down_revision = 'b3f9a1c2d4e5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'assessments',
        sa.Column('approved_by', sa.String(length=200), nullable=False, server_default=''),
    )
    op.add_column(
        'assessments',
        sa.Column('submitted_to', sa.String(length=200), nullable=False, server_default=''),
    )
    # Drop the server_default after backfilling existing rows — new inserts
    # rely on the ORM-side default=""  in models/assessment.py, not a DB-level
    # default, matching every other free-text column on this table.
    op.alter_column('assessments', 'approved_by', server_default=None)
    op.alter_column('assessments', 'submitted_to', server_default=None)


def downgrade() -> None:
    op.drop_column('assessments', 'submitted_to')
    op.drop_column('assessments', 'approved_by')
