"""link rescheduled follow-ups so each reschedule chain shows as one follow-up

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-09-30 16:30:00.000000

Before this, rescheduling created a second follow_ups row with no link to
the row it replaced, so the UI showed two near-identical cards. The new
`rescheduled_from_id` column links them. Existing reschedules are
backfilled: the old row's completed_at and the new row's created_at were
written in the same request, so they are matched on same assessment +
same type + timestamps within 10 seconds.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'f2a3b4c5d6e7'
down_revision = 'e1f2a3b4c5d6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'follow_ups',
        sa.Column('rescheduled_from_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('follow_ups.id'), nullable=True),
    )
    op.create_index(op.f('ix_follow_ups_rescheduled_from_id'), 'follow_ups', ['rescheduled_from_id'], unique=False)

    op.execute("""
        UPDATE follow_ups AS new_row
        SET rescheduled_from_id = (
            SELECT old_row.id
            FROM follow_ups AS old_row
            WHERE old_row.assessment_id = new_row.assessment_id
              AND old_row.follow_up_type = new_row.follow_up_type
              AND old_row.status = 'Rescheduled'
              AND old_row.id <> new_row.id
              AND old_row.completed_at IS NOT NULL
              AND ABS(EXTRACT(EPOCH FROM (new_row.created_at - old_row.completed_at))) < 10
              AND NOT EXISTS (
                  SELECT 1 FROM follow_ups AS other
                  WHERE other.rescheduled_from_id = old_row.id
              )
            ORDER BY ABS(EXTRACT(EPOCH FROM (new_row.created_at - old_row.completed_at)))
            LIMIT 1
        )
        WHERE new_row.rescheduled_from_id IS NULL
    """)


def downgrade() -> None:
    op.drop_index(op.f('ix_follow_ups_rescheduled_from_id'), table_name='follow_ups')
    op.drop_column('follow_ups', 'rescheduled_from_id')
