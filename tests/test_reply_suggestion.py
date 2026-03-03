"""Tests for reply suggestion (agent/reply_suggestion.py)."""

from unittest.mock import patch, MagicMock
import pytest
from auth.models import create_user, get_user_by_username
from messaging.models import get_or_create_conversation, add_message, get_messages
from agent.reply_suggestion import generate_reply_suggestion, on_message_received_for_reply_suggestion


def _user(username):
    create_user(username, "pass")
    return get_user_by_username(username)


@pytest.fixture
def conv_and_users():
    alice, bob = _user("alice"), _user("bob")
    conv = get_or_create_conversation(alice["id"], bob["id"])
    return conv, alice, bob


@patch("agent.reply_suggestion.OpenAI")
def test_generate_reply_suggestion_returns_llm_content(mock_openai, conv_and_users):
    mock_client = MagicMock()
    mock_openai.return_value = mock_client
    mock_client.chat.completions.create.return_value.choices = [
        MagicMock(message=MagicMock(content="Sounds good!"))
    ]
    conv, alice, bob = conv_and_users
    add_message(conv["id"], bob["id"], "How about 7pm?")
    recent = get_messages(conv["id"], limit=5)
    out = generate_reply_suggestion(recent, "How about 7pm?", alice["id"])
    assert "Sounds good" in out or out == "Sounds good!"


def test_generate_reply_suggestion_empty_message_returns_empty(conv_and_users):
    conv, alice, bob = conv_and_users
    assert generate_reply_suggestion([], "", alice["id"]) == ""


def test_on_message_received_creates_draft_and_calls_push(conv_and_users):
    conv, alice, bob = conv_and_users
    add_message(conv["id"], bob["id"], "Hey there")
    pushed = []

    def push(draft):
        pushed.append(draft)

    with patch("agent.reply_suggestion.generate_reply_suggestion", return_value="I'll be there"):
        on_message_received_for_reply_suggestion(
            "message_received",
            {"conversation_id": conv["id"], "sender_id": bob["id"], "content": "Hey there"},
            push_draft_to_ui=push,
        )
    assert len(pushed) == 1
    assert pushed[0]["content"] == "I'll be there"
    assert pushed[0]["sender_id"] == alice["id"]
    assert pushed[0]["rule_id"] is None


def test_on_message_received_wrong_event_does_nothing(conv_and_users):
    conv, alice, bob = conv_and_users
    pushed = []
    on_message_received_for_reply_suggestion(
        "message_sent",
        {"conversation_id": conv["id"], "sender_id": bob["id"], "content": "Hi"},
        push_draft_to_ui=pushed.append,
    )
    assert len(pushed) == 0
