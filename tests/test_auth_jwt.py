"""Unit tests for auth.jwt_utils."""

import pytest

from auth.jwt_utils import create_token, decode_token, ALGORITHM


SECRET = "test-jwt-secret-for-unit-tests-only-32chars"


def test_create_token_returns_string():
    """create_token returns a non-empty string."""
    token = create_token(1, "alice", secret=SECRET)
    assert isinstance(token, str)
    assert len(token) > 0


def test_decode_token_returns_payload():
    """decode_token returns payload with sub, username, iat, exp."""
    token = create_token(42, "bob", secret=SECRET)
    payload = decode_token(token, secret=SECRET)
    assert payload is not None
    assert payload["sub"] == "42"
    assert payload["username"] == "bob"
    assert "iat" in payload
    assert "exp" in payload


def test_decode_token_wrong_secret_returns_none():
    """decode_token with wrong secret returns None."""
    token = create_token(1, "alice", secret=SECRET)
    assert decode_token(token, secret="wrong-secret-at-least-32-characters-long") is None


def test_decode_token_tampered_returns_none():
    """Tampered token returns None."""
    token = create_token(1, "alice", secret=SECRET)
    tampered = token[:-1] + ("X" if token[-1] != "X" else "Y")
    assert decode_token(tampered, secret=SECRET) is None


def test_decode_token_empty_returns_none():
    """Empty or invalid token returns None."""
    assert decode_token("", secret=SECRET) is None
    assert decode_token("not.a.token", secret=SECRET) is None
