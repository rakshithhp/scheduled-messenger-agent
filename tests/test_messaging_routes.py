"""Unit tests for messaging API routes (conversations, messages)."""

import time
from unittest.mock import patch

import pytest

from agent.parser import ScheduledMessage
from app import app


@pytest.fixture
def client():
    """Flask test client."""
    app.config["TESTING"] = True
    return app.test_client()


def _register(client, username: str, **kwargs):
    """Register a user and return (response, token or None)."""
    payload = {
        "username": username,
        "password": "pass1234",
        "first_name": kwargs.get("first_name", "F"),
        "last_name": kwargs.get("last_name", "L"),
        "phone": kwargs.get("phone", "+15550000001"),
    }
    r = client.post("/auth/register", json=payload)
    data = r.get_json() if r.data else {}
    return r, data.get("token")


def _auth_headers(token: str):
    return {"Authorization": f"Bearer {token}"}


def test_list_conversations_empty(client):
    """GET /api/conversations with auth returns empty list when no conversations."""
    _, token = _register(client, "user1")
    r = client.get("/api/conversations", headers=_auth_headers(token))
    assert r.status_code == 200
    assert r.get_json() == []


def test_list_conversations_requires_auth(client):
    """GET /api/conversations without token returns 401."""
    r = client.get("/api/conversations")
    assert r.status_code == 401


def test_create_conversation_by_user_id(client):
    """POST /api/conversations with user_id creates or returns conversation."""
    _, token1 = _register(client, "alice", phone="+15550100001")
    _, token2 = _register(client, "bob", phone="+15550100002")
    from auth.models import get_user_by_username
    bob = get_user_by_username("bob")
    r = client.post(
        "/api/conversations",
        headers=_auth_headers(token1),
        json={"user_id": bob["id"]},
    )
    assert r.status_code == 201
    data = r.get_json()
    assert "id" in data
    assert "created_at" in data


def test_delete_conversation_requires_auth(client):
    """DELETE /api/conversations/<id> without token returns 401."""
    r = client.delete("/api/conversations/1")
    assert r.status_code == 401


def test_delete_conversation_success(client):
    """DELETE /api/conversations/<id> deletes conversation for participants."""
    _, token1 = _register(client, "delalice", phone="+15550101001")
    _, token2 = _register(client, "delbob", phone="+15550101002")
    from auth.models import get_user_by_username
    bob = get_user_by_username("delbob")
    r_conv = client.post(
        "/api/conversations",
        headers=_auth_headers(token1),
        json={"user_id": bob["id"]},
    )
    conv_id = r_conv.get_json()["id"]
    r_del = client.delete(f"/api/conversations/{conv_id}", headers=_auth_headers(token1))
    assert r_del.status_code == 200
    # After delete, listing conversations is empty
    r_list = client.get("/api/conversations", headers=_auth_headers(token1))
    assert r_list.status_code == 200
    assert r_list.get_json() == []


def test_create_conversation_with_self_returns_400(client):
    """POST /api/conversations with own user_id returns 400."""
    _, token = _register(client, "solo", phone="+15550100003")
    from auth.models import get_user_by_username
    me = get_user_by_username("solo")
    r = client.post(
        "/api/conversations",
        headers=_auth_headers(token),
        json={"user_id": me["id"]},
    )
    assert r.status_code == 400
    assert "yourself" in (r.get_json().get("error") or "").lower()


def test_add_contact_success(client):
    """POST /contacts with auth and alias+phone adds the contact and returns 200."""
    _, token = _register(client, "addcontact_user", phone="+15550999001")
    r = client.post(
        "/contacts",
        headers={**_auth_headers(token), "Content-Type": "application/json"},
        json={"alias": "wife", "phone": "+15551234567"},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("success") is True
    assert data.get("alias") == "wife"
    assert data.get("phone") == "+15551234567"
    from agent.contacts import load_contacts
    contacts = load_contacts()
    assert "wife" in contacts
    assert contacts["wife"] == "+15551234567"


def test_add_contact_requires_auth(client):
    """POST /contacts without token returns 401."""
    r = client.post(
        "/contacts",
        headers={"Content-Type": "application/json"},
        json={"alias": "mom", "phone": "+15559999999"},
    )
    assert r.status_code == 401


def test_add_contact_requires_alias_and_phone(client):
    """POST /contacts with missing alias or phone returns 400."""
    _, token = _register(client, "addcontact_user2", phone="+15550999002")
    r1 = client.post(
        "/contacts",
        headers={**_auth_headers(token), "Content-Type": "application/json"},
        json={"phone": "+15551111111"},
    )
    assert r1.status_code == 400
    r2 = client.post(
        "/contacts",
        headers={**_auth_headers(token), "Content-Type": "application/json"},
        json={"alias": "dad"},
    )
    assert r2.status_code == 400


def test_list_messages_requires_auth(client):
    """GET /api/conversations/1/messages without token returns 401."""
    r = client.get("/api/conversations/1/messages")
    assert r.status_code == 401


def test_list_messages_returns_404_for_unknown_conversation(client):
    """GET /api/conversations/99999/messages returns 404 when not a participant."""
    _, token = _register(client, "user1")
    r = client.get("/api/conversations/99999/messages", headers=_auth_headers(token))
    assert r.status_code == 404


def test_send_message_requires_auth(client):
    """POST /api/conversations/1/messages without token returns 401."""
    r = client.post(
        "/api/conversations/1/messages",
        json={"content": "Hi"},
    )
    assert r.status_code == 401


def test_send_message_returns_400_when_content_empty(client):
    """POST /api/conversations/<id>/messages with empty content returns 400."""
    _, token1 = _register(client, "a1", phone="+15550200001")
    _, token2 = _register(client, "b1", phone="+15550200002")
    from auth.models import get_user_by_username
    bob = get_user_by_username("b1")
    r_conv = client.post(
        "/api/conversations",
        headers=_auth_headers(token1),
        json={"user_id": bob["id"]},
    )
    conv_id = r_conv.get_json()["id"]
    r = client.post(
        f"/api/conversations/{conv_id}/messages",
        headers=_auth_headers(token1),
        json={"content": "   "},
    )
    assert r.status_code == 400


def test_send_message_returns_202_then_message_appears(client):
    """POST send_message returns 202 immediately; message is added in background and appears in GET."""
    with patch("app.parse_request") as mock_parse, patch("messaging.routes.expand_message_for_in_app") as mock_expand:
        mock_parse.return_value = ScheduledMessage(
            message="Hello there",
            contact_alias="bob",
            delay_seconds=0,
            raw_input="hello",
        )
        mock_expand.return_value = "Hello there"

        _, token1 = _register(client, "sender", phone="+15550300001")
        _, _ = _register(client, "recip", phone="+15550300002")
        from auth.models import get_user_by_username
        recip = get_user_by_username("recip")
        r_conv = client.post(
            "/api/conversations",
            headers=_auth_headers(token1),
            json={"user_id": recip["id"]},
        )
        conv_id = r_conv.get_json()["id"]

        r = client.post(
            f"/api/conversations/{conv_id}/messages",
            headers=_auth_headers(token1),
            json={"content": "hello"},
        )
        assert r.status_code == 202
        data = r.get_json()
        assert data.get("sending") is True
        assert data["conversation_id"] == conv_id

        # Background thread adds the message; wait briefly then GET
        time.sleep(1.0)
        r_list = client.get(
            f"/api/conversations/{conv_id}/messages",
            headers=_auth_headers(token1),
        )
        assert r_list.status_code == 200
        messages = r_list.get_json()
        assert len(messages) == 1
        assert messages[0]["content"] == "Hello there"


def test_send_message_scheduled_returns_202(client):
    """POST send_message returns 202 immediately; scheduled case is handled in background (WS notification)."""
    with patch("app.parse_request") as mock_parse, patch("messaging.routes.expand_message_for_in_app") as mock_expand:
        mock_parse.return_value = ScheduledMessage(
            message="Reminder",
            contact_alias="bob",
            delay_seconds=3600,
            raw_input="remind me in 1 hour",
        )
        mock_expand.return_value = "Reminder"

        _, token1 = _register(client, "sched_user", phone="+15550400001")
        _, _ = _register(client, "sched_recip", phone="+15550400002")
        from auth.models import get_user_by_username
        recip = get_user_by_username("sched_recip")
        r_conv = client.post(
            "/api/conversations",
            headers=_auth_headers(token1),
            json={"user_id": recip["id"]},
        )
        conv_id = r_conv.get_json()["id"]

        r = client.post(
            f"/api/conversations/{conv_id}/messages",
            headers=_auth_headers(token1),
            json={"content": "remind me in 1 hour"},
        )
        assert r.status_code == 202
        data = r.get_json()
        assert data.get("sending") is True
        assert data["conversation_id"] == conv_id
