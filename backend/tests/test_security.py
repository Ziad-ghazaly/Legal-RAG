"""Password + JWT + refresh token primitives."""

import os
import time

os.environ.setdefault("SECRET_KEY", "x" * 32)
os.environ.setdefault("ADMIN_PASSWORD", "y")

import pytest  # noqa: E402

from app.core.security import (  # noqa: E402
    ExpiredTokenError,
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    verify_password,
)


# --- passwords -----------------------------------------------------------


def test_hash_and_verify():
    h = hash_password("hunter2")
    assert h.startswith("$argon2")
    assert verify_password("hunter2", h) is True
    assert verify_password("wrong", h) is False


# --- JWT -----------------------------------------------------------------


def test_access_token_roundtrip():
    t = create_access_token(sub="user-1", role="admin")
    claims = decode_access_token(t)
    assert claims["sub"] == "user-1"
    assert claims["role"] == "admin"


def test_access_token_tampered_rejected():
    t = create_access_token(sub="user-1", role="user")
    tampered = t[:-4] + "AAAA"
    with pytest.raises(InvalidTokenError):
        decode_access_token(tampered)


def test_access_token_expired_rejected():
    t = create_access_token(sub="user-1", role="user", ttl_seconds=1)
    time.sleep(1.2)
    with pytest.raises(ExpiredTokenError):
        decode_access_token(t)


# --- refresh tokens ------------------------------------------------------


def test_refresh_token_pair():
    plain, h = new_refresh_token()
    assert len(plain) >= 43  # 32 bytes urlsafe base64 ≈ 43 chars
    assert hash_refresh_token(plain) == h
    plain2, h2 = new_refresh_token()
    assert plain != plain2
    assert h != h2
