"""add sector/position_role to candidates and candidate_profiles

Revision ID: d4e5f6a7b8c9
Revises: c7d8e9f0a1b2
Create Date: 2026-09-28 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'd4e5f6a7b8c9'
down_revision = 'c7d8e9f0a1b2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('candidates', sa.Column('sector', sa.String(length=50), nullable=True))
    op.add_column('candidates', sa.Column('position_role', sa.String(length=150), nullable=True))
    op.create_index(op.f('ix_candidates_sector'), 'candidates', ['sector'], unique=False)

    op.add_column('candidate_profiles', sa.Column('sector', sa.String(length=50), nullable=True))
    op.add_column('candidate_profiles', sa.Column('position_role', sa.String(length=150), nullable=True))


def downgrade() -> None:
    op.drop_column('candidate_profiles', 'position_role')
    op.drop_column('candidate_profiles', 'sector')

    op.drop_index(op.f('ix_candidates_sector'), table_name='candidates')
    op.drop_column('candidates', 'position_role')
    op.drop_column('candidates', 'sector')
