"""add gst_number and document_path to companies

Revision ID: c7d8e9f0a1b2
Revises: f1a2b3c4d5e6
Create Date: 2026-09-24 14:50:00.000000

Companies onboarded via the "Companies & roles" form now capture a GST
number and can have a supporting document (PDF/Word -- registration
certificate, agreement, etc.) attached, the same way a candidate's resume
is attached: a nullable path column pointing at a file on disk, written by
its own upload endpoint rather than the JSON create payload.
"""
from alembic import op
import sqlalchemy as sa


revision = 'c7d8e9f0a1b2'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'companies',
        sa.Column('gst_number', sa.String(length=15), nullable=False, server_default=''),
    )
    op.add_column(
        'companies',
        sa.Column('document_path', sa.String(length=500), nullable=True),
    )
    # server_default was only needed to backfill existing rows; drop it so
    # future inserts go through the model's Python-side default instead.
    op.alter_column('companies', 'gst_number', server_default=None)


def downgrade() -> None:
    op.drop_column('companies', 'document_path')
    op.drop_column('companies', 'gst_number')
