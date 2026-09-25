"""P1 corpus: integer collection ids, ingestion job columns, exact-lookup index.

Collections switch from UUID to integer ids because production_rules rule 3
(and its gold format) address collections as integers. All affected tables
are empty at the end of P0, so the FK columns are dropped and re-added.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-25
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("user_collections")
    op.drop_column("chunks", "collection_id")  # drops ix_chunks_embed_coll / validity index
    op.drop_column("documents", "collection_id")
    op.drop_table("collections")

    op.create_table(
        "collections",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), unique=True, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "user_collections",
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("collection_id", sa.Integer, sa.ForeignKey("collections.id", ondelete="CASCADE"), primary_key=True),
    )
    op.add_column("documents", sa.Column("collection_id", sa.Integer, sa.ForeignKey("collections.id"), nullable=True))
    op.add_column(
        "chunks",
        sa.Column("collection_id", sa.Integer, sa.ForeignKey("collections.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_chunks_embed_coll", "chunks", ["embedding_model", "collection_id"])
    op.create_index("ix_chunks_coll_status_validity", "chunks", ["collection_id", "status", "valid_from", "valid_to"])
    op.create_index("ix_documents_number_year", "documents", ["number", "year"])

    op.add_column("ingestion_jobs", sa.Column("collection_id", sa.Integer, sa.ForeignKey("collections.id"), nullable=True))
    op.add_column("ingestion_jobs", sa.Column("file_key", sa.Text, nullable=True))


def downgrade() -> None:
    raise NotImplementedError("0002 is forward-only (P0 tables were empty).")
