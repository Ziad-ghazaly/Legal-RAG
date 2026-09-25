"""P0 foundation: full schema, HNSW + BM25 indexes on empty tables, seed system_meta.

Revision ID: 0001
Revises:
Create Date: 2026-09-25
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_search")

    # --- auth ---
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("username", sa.String(128), unique=True, nullable=False, index=True),
        sa.Column("email", sa.String(320), unique=True, nullable=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32), nullable=False, server_default="user"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "collections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), unique=True, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "user_collections",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("collections.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("token_hash", sa.String(255), nullable=False, unique=True, index=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "system_meta",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.Text, nullable=False),
    )

    # --- corpus (empty in P0) ---
    op.create_table(
        "documents",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column("doc_type", sa.String(64), nullable=False, index=True),
        sa.Column("title_ar", sa.Text, nullable=False),
        sa.Column("number", sa.String(64), nullable=True),
        sa.Column("year", sa.Integer, nullable=True),
        sa.Column("issuing_authority", sa.String(255), nullable=True),
        sa.Column("issue_date", sa.Date, nullable=True),
        sa.Column("effective_date", sa.Date, nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="in_force", index=True),
        sa.Column("repealed_by", sa.String(255), nullable=True),
        sa.Column("gazette_ref", sa.String(255), nullable=True),
        sa.Column("legal_domain", postgresql.ARRAY(sa.String), nullable=True),
        sa.Column("language", sa.String(8), nullable=False, server_default="ar"),
        sa.Column("jurisdiction", sa.String(8), nullable=False, server_default="KW"),
        sa.Column("authority_level", sa.Float, nullable=False, server_default="0.5"),
        sa.Column("source_uri", sa.Text, nullable=True),
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("collections.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "units",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column("document_id", sa.String(255), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("unit_type", sa.String(32), nullable=False),
        sa.Column("path", postgresql.ARRAY(sa.String), nullable=True),
        sa.Column("article_number", sa.Integer, nullable=True, index=True),
        sa.Column("article_label", sa.String(128), nullable=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("valid_from", sa.Date, nullable=True),
        sa.Column("valid_to", sa.Date, nullable=True),
        sa.Column("amended_by", postgresql.ARRAY(sa.String), nullable=True),
    )
    op.create_index("ix_units_doc_article_valid", "units", ["document_id", "article_number", "valid_from"])

    op.create_table(
        "chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("unit_id", sa.String(255), sa.ForeignKey("units.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("document_id", sa.String(255), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("collections.id", ondelete="SET NULL"), nullable=True),
        sa.Column("chunk_kind", sa.String(32), nullable=False),
        sa.Column("context_header", sa.Text, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("text_norm", sa.Text, nullable=False),
        sa.Column("token_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("embedding_model", sa.String(128), nullable=False, index=True),
        sa.Column("doc_type", sa.String(64), nullable=False),
        sa.Column("authority_level", sa.Float, nullable=False, server_default="0.5"),
        sa.Column("status", sa.String(32), nullable=False, server_default="in_force"),
        sa.Column("valid_from", sa.Date, nullable=True),
        sa.Column("valid_to", sa.Date, nullable=True),
        sa.Column("legal_domain", postgresql.ARRAY(sa.String), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False, index=True),
    )
    # Add pgvector column separately so it's Postgres-native and precise.
    op.execute("ALTER TABLE chunks ADD COLUMN embedding vector(1024)")
    op.create_index("ix_chunks_embed_coll", "chunks", ["embedding_model", "collection_id"])
    op.create_index(
        "ix_chunks_coll_status_validity", "chunks",
        ["collection_id", "status", "valid_from", "valid_to"],
    )
    # HNSW on empty table (index bootstraps for later inserts).
    op.execute(
        "CREATE INDEX ix_chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 128)"
    )
    # BM25 index (pg_search). Tokenizer chosen to split Arabic.
    op.execute(
        """
        CREATE INDEX ix_chunks_text_norm_bm25 ON chunks
        USING bm25 (id, text_norm)
        WITH (
            key_field='id',
            text_fields='{"text_norm": {"tokenizer": {"type":"icu"}}}'
        )
        """
    )

    # --- reviews ---
    op.create_table(
        "reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("question", sa.Text, nullable=True),
        sa.Column("opinion_text", sa.Text, nullable=False, server_default=""),
        sa.Column("file_key", sa.Text, nullable=True),
        sa.Column("as_of_date", sa.Date, nullable=True),
        sa.Column("collection_scope", postgresql.ARRAY(sa.String), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="processing", index=True),
        sa.Column("score", sa.Integer, nullable=True),
        sa.Column("config_snapshot", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("review_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("text_ar", sa.Text, nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("materiality", sa.String(32), nullable=False, server_default="supporting"),
        sa.Column("cited_refs", postgresql.JSONB, nullable=True),
        sa.Column("verdict", sa.String(32), nullable=True),
        sa.Column("weight", sa.Integer, nullable=False, server_default="1"),
        sa.Column("reasoning_ar", sa.Text, nullable=True),
    )
    op.create_table(
        "claim_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stance", sa.String(32), nullable=False),
        sa.Column("quote_ar", sa.Text, nullable=False),
        sa.Column("quote_verified", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("authority_level", sa.Float, nullable=False, server_default="0.5"),
        sa.Column("source_status", sa.String(32), nullable=False, server_default="in_force"),
        sa.Column("blocking", sa.Boolean, nullable=False, server_default=sa.text("false")),
    )
    op.create_table(
        "review_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("review_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("content", postgresql.JSONB, nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("review_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("approver_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # --- ops ---
    op.create_table(
        "llm_calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("review_id", postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("prompt_version", sa.String(64), nullable=False, server_default=""),
        sa.Column("input_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("latency_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("request_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(64), nullable=False),
        sa.Column("target_id", sa.String(255), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending", index=True),
        sa.Column("doc_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("submitted_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("stats", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "eval_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("metrics", postgresql.JSONB, nullable=False),
        sa.Column("config_snapshot", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # --- seed system_meta ---
    op.execute(
        """
        INSERT INTO system_meta (key, value) VALUES
        ('embedding_model', 'BAAI/bge-m3'),
        ('embedding_dim', '1024'),
        ('normalizer_version', 'v1'),
        ('schema_version', '0001')
        """
    )


def downgrade() -> None:
    raise NotImplementedError(
        "0001 is the P0 baseline; recover by dropping the volume `v3_postgres_data`."
    )
