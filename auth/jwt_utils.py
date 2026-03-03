"""JWT create/verify using app secret."""

import os
import time
from typing import Any

import jwt

# Default for dev; must set JWT_SECRET in production
SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_EXPIRY_DAYS = 7


def create_token(user_id: int, username: str, secret: str | None = None) -> str:
    """Issue a JWT for the user. secret overrides env (e.g. from Flask app config)."""
    key = secret or SECRET
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "username": username,
        "iat": now,
        "exp": now + ACCESS_EXPIRY_DAYS * 24 * 3600,
    }
    return jwt.encode(payload, key, algorithm=ALGORITHM)


def decode_token(token: str, secret: str | None = None) -> dict[str, Any] | None:
    """Decode and validate JWT; return payload or None. secret overrides env."""
    key = secret or SECRET
    try:
        payload = jwt.decode(
            token, key, algorithms=[ALGORITHM],
            leeway=60,  # 60s clock skew tolerance
        )
        return payload
    except jwt.InvalidTokenError:
        return None
