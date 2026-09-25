"""Config loads env vars and enforces required ones."""

import pytest

from app.core.config import Settings


def test_settings_loads_env(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-32-bytes-hex-string" * 2)
    monkeypatch.setenv("ADMIN_PASSWORD", "test-admin-pass")
    monkeypatch.setenv("POSTGRES_PASSWORD", "test-db-pw")
    s = Settings()
    assert s.secret_key.startswith("test-secret")
    assert s.embedding_model == "BAAI/bge-m3"
    assert s.embedding_dim == 1024
    assert "postgresql+asyncpg://" in s.postgres_dsn


def test_settings_rejects_empty_secret_key(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "")
    monkeypatch.setenv("ADMIN_PASSWORD", "x")
    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings()


def test_settings_rejects_placeholder_secret_key(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "CHANGE_ME")
    monkeypatch.setenv("ADMIN_PASSWORD", "x")
    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings()
