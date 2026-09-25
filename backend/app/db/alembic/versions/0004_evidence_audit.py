"""claim_evidence survives re-ingestion: chunk_id nullable, FK ON DELETE SET NULL.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-25
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("claim_evidence_chunk_id_fkey", "claim_evidence", type_="foreignkey")
    op.alter_column("claim_evidence", "chunk_id", nullable=True)
    op.create_foreign_key(
        "claim_evidence_chunk_id_fkey",
        "claim_evidence",
        "chunks",
        ["chunk_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    raise NotImplementedError("forward-only")
