"""Unit tests for auth.models."""

import pytest

from auth.models import (
    create_user,
    get_user_by_username,
    get_user_by_id,
    verify_password,
)


def test_create_user_returns_user_dict():
    """create_user returns user dict with id, username, created_at and profile fields."""
    user = create_user(
        "alice",
        "password123",
        first_name="Alice",
        last_name="Smith",
        phone="+15551234567",
    )
    assert user is not None
    assert user["id"] is not None
    assert user["username"] == "alice"
    assert "created_at" in user
    assert user["first_name"] == "Alice"
    assert user["last_name"] == "Smith"
    assert user["phone"] == "+15551234567"


def test_create_user_normalizes_username_to_lowercase():
    """Username is stored and returned in lowercase."""
    user = create_user("Bob", "pass1234", first_name="B", last_name="B", phone="1")
    assert user is not None
    assert user["username"] == "bob"


def test_create_user_returns_none_for_duplicate_username():
    """Second create_user with same username returns None."""
    create_user("charlie", "pass1234", first_name="C", last_name="C", phone="1")
    second = create_user("charlie", "other", first_name="C2", last_name="C2", phone="2")
    assert second is None


def test_create_user_returns_none_for_empty_username():
    """Empty or whitespace username returns None."""
    assert create_user("", "pass1234", first_name="X", last_name="X", phone="1") is None
    assert create_user("  ", "pass1234", first_name="X", last_name="X", phone="1") is None


def test_create_user_returns_none_for_empty_password():
    """Empty password returns None."""
    assert create_user("dave", "", first_name="D", last_name="D", phone="1") is None


def test_get_user_by_username_finds_user():
    """get_user_by_username returns user with password_hash."""
    create_user("eve", "secret123", first_name="Eve", last_name="E", phone="1")
    user = get_user_by_username("eve")
    assert user is not None
    assert user["username"] == "eve"
    assert "password_hash" in user
    assert user["first_name"] == "Eve"


def test_get_user_by_username_case_insensitive():
    """Lookup is case-insensitive."""
    create_user("Frank", "pass1234", first_name="F", last_name="F", phone="1")
    assert get_user_by_username("frank") is not None
    assert get_user_by_username("FRANK") is not None


def test_get_user_by_username_returns_none_for_unknown():
    """Unknown username returns None."""
    assert get_user_by_username("nosuchuser") is None


def test_get_user_by_id_returns_user_without_password_hash():
    """get_user_by_id returns user and does not include password_hash."""
    created = create_user("grace", "pass1234", first_name="G", last_name="G", phone="1")
    user = get_user_by_id(created["id"])
    assert user is not None
    assert user["username"] == "grace"
    assert user.get("password_hash") is None
    assert "first_name" in user


def test_get_user_by_id_returns_none_for_unknown_id():
    """Unknown id returns None."""
    assert get_user_by_id(99999) is None


def test_verify_password_success():
    """verify_password returns True for correct password."""
    create_user("henry", "correcthorse", first_name="H", last_name="H", phone="1")
    user = get_user_by_username("henry")
    assert verify_password(user, "correcthorse") is True


def test_verify_password_failure():
    """verify_password returns False for wrong password."""
    create_user("ivan", "mypassword", first_name="I", last_name="I", phone="1")
    user = get_user_by_username("ivan")
    assert verify_password(user, "wrongpassword") is False
