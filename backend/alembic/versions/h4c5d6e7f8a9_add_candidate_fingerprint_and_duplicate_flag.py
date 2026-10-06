"""add file_sha256 + possible_duplicate_of to candidates

Revision ID: h4c5d6e7f8a9
Revises: g3b4c5d6e7f8
Create Date: 2026-10-01 15:30:00.000000

file_sha256 lets an exact copy of an already-uploaded resume be skipped at
upload time. Existing candidates are backfilled by hashing their resume
file on disk (best-effort: a missing/unreadable file just stays NULL).

possible_duplicate_of is backfilled for existing candidates that share an
email (case-insensitive, ignoring placeholder emails) or the last 10 phone
digits with an earlier active candidate.
"""
import hashlib
import os

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'h4c5d6e7f8a9'
down_revision = 'g3b4c5d6e7f8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('candidates', sa.Column('file_sha256', sa.String(length=64), nullable=True))
    op.create_index(op.f('ix_candidates_file_sha256'), 'candidates', ['file_sha256'], unique=False)
    op.add_column('candidates', sa.Column('possible_duplicate_of', postgresql.UUID(as_uuid=True),
                                          sa.ForeignKey('candidates.id'), nullable=True))
    op.create_index(op.f('ix_candidates_possible_duplicate_of'), 'candidates', ['possible_duplicate_of'], unique=False)

    conn = op.get_bind()

    # --- backfill file fingerprints from the files on disk ---
    rows = conn.execute(sa.text(
        "SELECT id, file_path FROM candidates WHERE file_path IS NOT NULL AND file_sha256 IS NULL"
    )).fetchall()
    for cid, path in rows:
        try:
            if path and os.path.isfile(path):
                with open(path, 'rb') as fh:
                    digest = hashlib.sha256(fh.read()).hexdigest()
                conn.execute(sa.text("UPDATE candidates SET file_sha256 = :h WHERE id = :id"),
                             {"h": digest, "id": cid})
        except OSError:
            pass  # unreadable file: leave NULL

    # --- backfill possible duplicates (same email, same phone, or same file) ---
    conn.execute(sa.text("""
        UPDATE candidates AS c
        SET possible_duplicate_of = (
            SELECT o.id FROM candidates AS o
            WHERE o.id <> c.id
              AND o.deleted_at IS NULL
              AND o.added_on < c.added_on
              AND (
                    (c.email NOT LIKE '%@pending.local' AND c.email <> ''
                     AND lower(o.email) = lower(c.email))
                 OR (length(regexp_replace(c.phone, '[^0-9]', '', 'g')) >= 10
                     AND right(regexp_replace(o.phone, '[^0-9]', '', 'g'), 10)
                       = right(regexp_replace(c.phone, '[^0-9]', '', 'g'), 10))
                 OR (c.file_sha256 IS NOT NULL AND o.file_sha256 = c.file_sha256)
              )
            ORDER BY o.added_on
            LIMIT 1
        )
        WHERE c.deleted_at IS NULL AND c.possible_duplicate_of IS NULL
    """))


def downgrade() -> None:
    op.drop_index(op.f('ix_candidates_possible_duplicate_of'), table_name='candidates')
    op.drop_column('candidates', 'possible_duplicate_of')
    op.drop_index(op.f('ix_candidates_file_sha256'), table_name='candidates')
    op.drop_column('candidates', 'file_sha256')
