"""add status_detail / status_updated_at to candidates (bulk-upload progress)

Revision ID: g3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-10-01 11:30:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'g3b4c5d6e7f8'
down_revision = 'f2a3b4c5d6e7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('candidates', sa.Column('status_detail', sa.String(length=300), nullable=False, server_default=''))
    op.add_column('candidates', sa.Column('status_updated_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('candidates', 'status_updated_at')
    op.drop_column('candidates', 'status_detail')
