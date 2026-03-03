"""Tests for conversation state (agent/conversation_state.py)."""

import pytest
from auth.models import create_user, get_user_by_username
from messaging.models import get_or_create_conversation, add_message
from agent.conversation_state import get_conversation_state


def _user(username):
    create_user(username, "pass")
    return get_user_by_username(username)


@pytest.fixture
def conv_and_users():
    alice, bob = _user("alice"), _user("bob")
    conv = get_or_create_conversation(alice["id"], bob["id"])
    return conv, alice, bob


def test_empty_conversation_returns_empty_state(conv_and_users):
    conv, alice, bob = conv_and_users
    state = get_conversation_state(conv["id"], alice["id"])
    assert state["message_count"] == 0
    assert state["initiation_ratio"] == 0.5
    assert state["avg_reply_seconds"] is None


def test_conversation_state_has_expected_keys(conv_and_users):
    conv, alice, bob = conv_and_users
    add_message(conv["id"], alice["id"], "Hi")
    add_message(conv["id"], bob["id"], "Hello")
    state = get_conversation_state(conv["id"], alice["id"])
    assert "initiation_ratio" in state
    assert "avg_reply_seconds" in state
    assert "last_sentiment" in state
    assert "unanswered_messages" in state
    assert state["message_count"] == 2


def test_unanswered_messages_trailing_from_other(conv_and_users):
    conv, alice, bob = conv_and_users
    add_message(conv["id"], alice["id"], "Hi")
    add_message(conv["id"], bob["id"], "Hey")
    add_message(conv["id"], bob["id"], "You there?")
    state = get_conversation_state(conv["id"], alice["id"])
    assert state["unanswered_messages"] == 2
