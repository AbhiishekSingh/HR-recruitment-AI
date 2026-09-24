"""fix candidate_profiles.total_experience_years column type

Revision ID: f1a2b3c4d5e6
Revises: e73bd471910d
Create Date: 2026-09-21 16:25:00.000000

The model has always type-hinted this as `float | None`
(models/candidate_profile.py), but the column itself was created as
INTEGER. Postgres silently truncates a float written through most drivers,
but asyncpg (used here) is strict about parameter types and raises
`DataError: invalid input for query argument: expected int, got float`
the first time GPT-5 extracts a non-whole-number experience value (e.g.
4.5 years) -- which is a completely normal thing for it to return, so this
was a matter of when, not if, ingestion broke on a real resume.
"""
from alembic import op
import sqlalchemy as sa


revision = 'f1a2b3c4d5e6'
down_revision = 'e73bd471910d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        'candidate_profiles',
        'total_experience_years',
        type_=sa.Float(),
        existing_type=sa.Integer(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        'candidate_profiles',
        'total_experience_years',
        type_=sa.Integer(),
        existing_type=sa.Float(),
        existing_nullable=True,
    )
