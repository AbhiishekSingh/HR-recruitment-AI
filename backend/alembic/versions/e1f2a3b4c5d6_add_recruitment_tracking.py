"""add recruitment tracking: pipeline stage, selection/joining, invoice,
follow-ups, stage history, company is_active

Revision ID: e1f2a3b4c5d6
Revises: d4e5f6a7b8c9
Create Date: 2026-09-30 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'e1f2a3b4c5d6'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- assessments: tracking columns (all nullable / defaulted so existing rows stay valid) ---
    op.add_column('assessments', sa.Column('stage', sa.String(length=30), nullable=False, server_default=''))
    op.add_column('assessments', sa.Column('submitted_on', sa.DateTime(timezone=True), nullable=True))
    op.add_column('assessments', sa.Column('offered_ctc', sa.Float(), nullable=True))
    op.add_column('assessments', sa.Column('joining_date', sa.Date(), nullable=True))
    op.add_column('assessments', sa.Column('invoice_raised', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('assessments', sa.Column('invoice_date', sa.Date(), nullable=True))
    op.add_column('assessments', sa.Column('invoice_amount', sa.Float(), nullable=True))
    op.create_index(op.f('ix_assessments_stage'), 'assessments', ['stage'], unique=False)

    # Backfill: anything already shortlisted / sent to client gets a stage so
    # it shows up on the new Shortlisted page straight away.
    op.execute("UPDATE assessments SET stage = 'Submitted', submitted_on = updated_at "
               "WHERE sent_to_client = true AND stage = ''")
    op.execute("UPDATE assessments SET stage = 'Shortlisted' "
               "WHERE final_status = 'Share to Client' AND stage = ''")

    # --- companies: Active/Inactive label ---
    op.add_column('companies', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()))

    # --- follow_ups ---
    op.create_table(
        'follow_ups',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('assessment_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('assessments.id'), nullable=False),
        sa.Column('candidate_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('candidates.id'), nullable=False),
        sa.Column('job_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('job_postings.id'), nullable=False),
        sa.Column('follow_up_type', sa.String(length=40), nullable=False, server_default='General Follow-up'),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='Scheduled'),
        sa.Column('notes', sa.String(), nullable=False, server_default=''),
        sa.Column('outcome', sa.String(), nullable=False, server_default=''),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    )
    for col in ('assessment_id', 'candidate_id', 'job_id', 'scheduled_at', 'status', 'deleted_at'):
        op.create_index(op.f(f'ix_follow_ups_{col}'), 'follow_ups', [col], unique=False)

    # --- assessment_stage_history ---
    op.create_table(
        'assessment_stage_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('assessment_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('assessments.id'), nullable=False),
        sa.Column('from_stage', sa.String(length=30), nullable=False, server_default=''),
        sa.Column('to_stage', sa.String(length=30), nullable=False),
        sa.Column('note', sa.String(), nullable=False, server_default=''),
        sa.Column('changed_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('changed_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(op.f('ix_assessment_stage_history_assessment_id'), 'assessment_stage_history', ['assessment_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_assessment_stage_history_assessment_id'), table_name='assessment_stage_history')
    op.drop_table('assessment_stage_history')

    for col in ('assessment_id', 'candidate_id', 'job_id', 'scheduled_at', 'status', 'deleted_at'):
        op.drop_index(op.f(f'ix_follow_ups_{col}'), table_name='follow_ups')
    op.drop_table('follow_ups')

    op.drop_column('companies', 'is_active')

    op.drop_index(op.f('ix_assessments_stage'), table_name='assessments')
    for col in ('invoice_amount', 'invoice_date', 'invoice_raised', 'joining_date',
                'offered_ctc', 'submitted_on', 'stage'):
        op.drop_column('assessments', col)
