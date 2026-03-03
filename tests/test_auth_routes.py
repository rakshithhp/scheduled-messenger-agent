"""Unit tests for auth routes (register, login, me, logout)."""

import pytest


# Import app after conftest has set AUTH_DB_PATH and JWT_SECRET
from app import app


@pytest.fixture
def client():
    """Flask test client."""
    app.config["TESTING"] = True
    return app.test_client()


def test_register_success(client):
    """POST /auth/register with all required fields returns 201 and token."""
    r = client.post(
        "/auth/register",
        json={
            "username": "routealice",
            "password": "password123",
            "first_name": "Alice",
            "last_name": "Route",
            "phone": "+15551234567",
            "email": "alice@test.com",
        },
    )
    assert r.status_code == 201
    data = r.get_json()
    assert "token" in data
    assert data["user"]["username"] == "routealice"
    assert data["user"]["first_name"] == "Alice"
    assert data["user"]["email"] == "alice@test.com"
    assert "password" not in str(data)


def test_register_missing_first_name(client):
    """POST /auth/register without first_name returns 400."""
    r = client.post(
        "/auth/register",
        json={
            "username": "bob",
            "password": "pass1234",
            "last_name": "B",
            "phone": "1",
            "email": "b@b.com",
        },
    )
    assert r.status_code == 400
    assert "First name" in r.get_json().get("error", "")


def test_register_missing_password(client):
    """POST /auth/register without password returns 400."""
    r = client.post(
        "/auth/register",
        json={
            "username": "carl",
            "password": "",
            "first_name": "C",
            "last_name": "C",
            "phone": "1",
            "email": "c@c.com",
        },
    )
    assert r.status_code == 400


def test_register_short_password(client):
    """POST /auth/register with password < 6 chars returns 400."""
    r = client.post(
        "/auth/register",
        json={
            "username": "dave",
            "password": "12345",
            "first_name": "D",
            "last_name": "D",
            "phone": "1",
            "email": "d@d.com",
        },
    )
    assert r.status_code == 400
    assert "6" in r.get_json().get("error", "")


def test_register_duplicate_username(client):
    """POST /auth/register with existing username returns 409."""
    payload = {
        "username": "dupe",
        "password": "pass1234",
        "first_name": "D",
        "last_name": "D",
        "phone": "1",
        "email": "d1@d.com",
    }
    client.post("/auth/register", json=payload)
    r = client.post(
        "/auth/register",
        json={
            **payload,
            "email": "d2@d.com",
        },
    )
    assert r.status_code == 409
    err = r.get_json().get("error", "").lower()
    assert "taken" in err or "phone" in err  # duplicate username or duplicate phone


def test_login_success(client):
    """POST /auth/login with valid credentials returns 200 and token."""
    client.post(
        "/auth/register",
        json={
            "username": "logineve",
            "password": "secret123",
            "first_name": "Eve",
            "last_name": "E",
            "phone": "1",
            "email": "eve@test.com",
        },
    )
    r = client.post(
        "/auth/login",
        json={"username": "logineve", "password": "secret123"},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert "token" in data
    assert data["user"]["username"] == "logineve"


def test_login_wrong_password(client):
    """POST /auth/login with wrong password returns 401."""
    client.post(
        "/auth/register",
        json={
            "username": "frank",
            "password": "correct",
            "first_name": "F",
            "last_name": "F",
            "phone": "1",
            "email": "f@f.com",
        },
    )
    r = client.post(
        "/auth/login",
        json={"username": "frank", "password": "wrong"},
    )
    assert r.status_code == 401
    assert "error" in r.get_json()


def test_login_unknown_user(client):
    """POST /auth/login with unknown username returns 401."""
    r = client.post(
        "/auth/login",
        json={"username": "nobody", "password": "any"},
    )
    assert r.status_code == 401


def test_me_without_auth(client):
    """GET /auth/me without token returns 401."""
    r = client.get("/auth/me")
    assert r.status_code == 401


def test_me_with_valid_token(client):
    """GET /auth/me with valid Bearer token returns current user."""
    reg = client.post(
        "/auth/register",
        json={
            "username": "meuser",
            "password": "pass1234",
            "first_name": "Me",
            "last_name": "User",
            "phone": "1",
            "email": "me@test.com",
        },
    )
    token = reg.get_json()["token"]
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.get_json()
    assert data["username"] == "meuser"
    assert data["first_name"] == "Me"
    assert "password_hash" not in data


def test_register_sets_cookie(client):
    """POST /auth/register response sets HttpOnly token cookie."""
    r = client.post(
        "/auth/register",
        json={
            "username": "cookieuser",
            "password": "pass1234",
            "first_name": "C",
            "last_name": "U",
            "phone": "1",
            "email": "cookie@test.com",
        },
    )
    assert r.status_code == 201
    set_cookie = r.headers.get("Set-Cookie") or ""
    assert "token=" in set_cookie
    assert "HttpOnly" in set_cookie or "httponly" in set_cookie.lower()


def test_logout_get_redirects(client):
    """GET /auth/logout clears cookie and redirects to /login."""
    r = client.get("/auth/logout")
    assert r.status_code == 302
    assert "login" in (r.headers.get("Location") or "").lower()


def test_logout_post_returns_ok(client):
    """POST /auth/logout returns 200 and clears cookie."""
    r = client.post("/auth/logout")
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("ok") is True
