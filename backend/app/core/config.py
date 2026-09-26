"""Central configuration. Single source of truth. Read from env only."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PLACEHOLDER_SECRETS = {"", "CHANGE_ME", "changeme", "secret", "REPLACE_ME"}


class Settings(BaseSettings):
    """Loaded once at process boot; immutable afterward."""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    # --- required ---
    secret_key: str = Field(...)
    admin_password: str = Field(..., min_length=1)
    anthropic_api_key: str = Field(default="")
    claude_model: str = "claude-sonnet-4-5"  # brief §4; configurable via CLAUDE_MODEL

    # --- database ---
    postgres_host: str = "v3_pgbouncer"
    postgres_port: int = 5432
    postgres_db: str = "legalrag"
    postgres_user: str = "legalrag"
    postgres_password: str = "legalrag"

    # --- redis / s3 / tei ---
    redis_url: str = "redis://v3_redis:6379/0"
    s3_endpoint_url: str = "http://minio:9000"  # alias: botocore rejects "_" in hostnames
    s3_access_key: str = "legalrag"
    s3_secret_key: str = "legalrag-secret"
    s3_bucket_uploads: str = "v3-uploads"
    s3_bucket_debug: str = "v3-ingestion-debug"
    tei_embed_url: str = "http://v3_tei_embed:80"
    tei_rerank_url: str = "http://v3_tei_rerank:80"
    # CPU dev: ~1.6 s per 512-token pair; GPU prod: tens of ms.
    tei_rerank_timeout_s: float = 120.0
    tei_embed_timeout_s: float = 600.0  # ingestion batches under load on CPU TEI

    # --- reviews ---
    daily_review_limit: int = 50
    max_upload_mb: int = 20

    # --- rule 1 invariant ---
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024

    # --- observability ---
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    otel_service_name: str = "legal-rag-v3-api"

    # --- derived ---
    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def postgres_dsn_sync(self) -> str:
        """Sync DSN for Alembic migrations."""
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @field_validator("secret_key")
    @classmethod
    def _reject_placeholder_secret(cls, v: str) -> str:
        if v.strip() in _PLACEHOLDER_SECRETS or len(v) < 16:
            raise ValueError(
                "SECRET_KEY must be a strong random value (>= 16 chars, not a placeholder). "
                "SECRET_KEY يجب أن يكون قيمة عشوائية قوية"
            )
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
