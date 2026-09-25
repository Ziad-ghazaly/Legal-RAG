"""Password hashing (argon2id) + JWT access tokens + refresh tokens."""

import hashlib
import secrets
import time
import uuid

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import get_settings

ACCESS_TOKEN_TTL_SECONDS = 15 * 60          # 15 minutes
REFRESH_TOKEN_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days
JWT_ALG = "HS256"

_ph = PasswordHasher()


class InvalidTokenError(Exception):
    """Signature bad, format bad, key wrong."""


class ExpiredTokenError(InvalidTokenError):
    """Token is well-formed but past its exp."""


# --- passwords -----------------------------------------------------------


def hash_password(plaintext: str) -> str:
    return _ph.hash(plaintext)


def verify_password(plaintext: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, plaintext)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


# --- access tokens -------------------------------------------------------


def create_access_token(sub: str, role: str, ttl_seconds: int = ACCESS_TOKEN_TTL_SECONDS) -> str:
    now = int(time.time())
    payload = {
        "sub": sub,
        "role": role,
        "iat": now,
        "exp": now + ttl_seconds,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, get_settings().secret_key, algorithm=JWT_ALG)


def decode_access_token(token: str) -> dict[str, object]:
    try:
        return jwt.decode(token, get_settings().secret_key, algorithms=[JWT_ALG])
    except jwt.ExpiredSignatureError as e:
        raise ExpiredTokenError("Access token expired") from e
    except jwt.InvalidTokenError as e:
        raise InvalidTokenError(str(e)) from e


# --- refresh tokens ------------------------------------------------------


def new_refresh_token() -> tuple[str, str]:
    """Return (plaintext, sha256_hex). Store the hash; give the plaintext to the client."""
    plaintext = secrets.token_urlsafe(32)
    return plaintext, hash_refresh_token(plaintext)


def hash_refresh_token(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
