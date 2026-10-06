"""add job_postings.scoring_config (skill groups) and ai_usage_log

Revision ID: j6e7f8a9b0c1
Revises: i5d6e7f8a9b0
Create Date: 2026-10-05 12:30:00.000000

Existing jobs get scoring_config = {} which means "use the automatic
default groups built from required skills" -- nothing to backfill.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'j6e7f8a9b0c1'
down_revision = 'i5d6e7f8a9b0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('job_postings', sa.Column('scoring_config', postgresql.JSONB(astext_type=sa.Text()),
                                            nullable=False, server_default=sa.text("'{}'::jsonb")))

    op.create_table(
        'ai_usage_log',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('task', sa.String(length=40), nullable=False),
        sa.Column('model', sa.String(length=100), nullable=False),
        sa.Column('input_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('cached_input_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('output_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('reasoning_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('cost_usd', sa.Float(), nullable=False, server_default='0'),
        sa.Column('priced', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('job_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('job_postings.id'), nullable=True),
        sa.Column('candidate_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('candidates.id'), nullable=True),
    )
    for col in ('created_at', 'task', 'job_id', 'candidate_id'):
        op.create_index(op.f(f'ix_ai_usage_log_{col}'), 'ai_usage_log', [col], unique=False)


def downgrade() -> None:
    for col in ('created_at', 'task', 'job_id', 'candidate_id'):
        op.drop_index(op.f(f'ix_ai_usage_log_{col}'), table_name='ai_usage_log')
    op.drop_table('ai_usage_log')
    op.drop_column('job_postings', 'scoring_config')
