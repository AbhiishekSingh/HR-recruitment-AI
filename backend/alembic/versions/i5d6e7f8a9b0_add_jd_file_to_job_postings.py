"""add jd_file_path / jd_file_name to job_postings (upload JD file)

Revision ID: i5d6e7f8a9b0
Revises: h4c5d6e7f8a9
Create Date: 2026-10-03 15:30:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'i5d6e7f8a9b0'
down_revision = 'h4c5d6e7f8a9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('job_postings', sa.Column('jd_file_path', sa.String(length=500), nullable=True))
    op.add_column('job_postings', sa.Column('jd_file_name', sa.String(length=300), nullable=True))


def downgrade() -> None:
    op.drop_column('job_postings', 'jd_file_name')
    op.drop_column('job_postings', 'jd_file_path')
