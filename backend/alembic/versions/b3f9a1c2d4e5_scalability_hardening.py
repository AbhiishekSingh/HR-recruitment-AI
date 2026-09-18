"""scalability hardening: match_results upsert key + index, soft deletes

Revision ID: b3f9a1c2d4e5
Revises: a6a84d0d04aa
Create Date: 2026-09-18 11:30:00.000000

Adds, without changing any existing table's shape otherwise:
  1. match_results.requirements_hash — lets Stage 2 scoring dedupe/upsert
     on (job_id, candidate_id) instead of accumulating a new row every
     time a job is re-matched.
  2. Unique constraint on match_results(job_id, candidate_id) — one
     current score per pair; re-scoring updates the row in place.
  3. Composite index on match_results(job_id, score DESC) — the pipeline
     view's most-hit query (sorted shortlist for one job).
  4. deleted_at (nullable, soft-delete) on companies, candidates,
     job_postings, assessments — added now while these tables are still
     small, so a future "don't hard-delete" requirement doesn't need a
     harder retrofit once foreign keys are relied on for cascade deletes.
"""
from alembic import op
import sqlalchemy as sa

revision = 'b3f9a1c2d4e5'
down_revision = 'a6a84d0d04aa'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. requirements_hash on match_results (nullable at add-time; existing
    #    rows have no hash to backfill from, so they're left null — the
    #    next real match run will populate/replace them via the upsert path)
    op.add_column(
        'match_results',
        sa.Column('requirements_hash', sa.String(length=64), nullable=True),
    )

    # 2. Upsert key: one row per (job, candidate). If duplicate pairs
    #    already exist from earlier test runs, dedupe before adding the
    #    constraint (keep the most recently scored row per pair).
    op.execute("""
        DELETE FROM match_results mr
        USING match_results newer
        WHERE mr.job_id = newer.job_id
          AND mr.candidate_id = newer.candidate_id
          AND mr.scored_at < newer.scored_at
    """)
    op.create_unique_constraint(
        'uq_match_results_job_candidate', 'match_results', ['job_id', 'candidate_id']
    )

    # 3. Composite index for the pipeline's sorted-shortlist query
    op.create_index(
        'ix_match_results_job_score',
        'match_results',
        ['job_id', sa.text('score DESC')],
    )

    # 4. Soft-delete columns
    for table in ('companies', 'candidates', 'job_postings', 'assessments'):
        op.add_column(
            table,
            sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            f'ix_{table}_deleted_at', table, ['deleted_at'], unique=False
        )


def downgrade() -> None:
    for table in ('companies', 'candidates', 'job_postings', 'assessments'):
        op.drop_index(f'ix_{table}_deleted_at', table_name=table)
        op.drop_column(table, 'deleted_at')

    op.drop_index('ix_match_results_job_score', table_name='match_results')
    op.drop_constraint('uq_match_results_job_candidate', 'match_results', type_='unique')
    op.drop_column('match_results', 'requirements_hash')
