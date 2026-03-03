"""Unit tests for messaging models (conversations, messages)."""

import pytest

from auth.models import create_user
from messaging.models import (
    get_or_create_conversation,
    get_conversation,
    get_conversations_for_user,
    add_message,
    get_messages,
    get_participant_ids,
    get_max_message_id,
    get_unread_count,
    set_last_read,
)


def _make_user(username: str, **kwargs) -> dict:
    """Create a user and return the user dict."""
    create_user(username, "pass1234", **kwargs)
    from auth.models import get_user_by_username
    return get_user_by_username(username)


@pytest.fixture
def two_users():
    """Two users for conversation tests."""
    a = _make_user("alice", first_name="Alice", phone="+15550100001")
    b = _make_user("bob", first_name="Bob", phone="+15550100002")
    return a, b


def test_get_or_create_conversation_creates_new(two_users):
    """get_or_create_conversation creates a new conversation between two users."""
    alice, bob = two_users
    conv = get_or_create_conversation(alice["id"], bob["id"])
    assert conv["id"] is not None
    assert "created_at" in conv


def test_get_or_create_conversation_same_pair_returns_same(two_users):
    """get_or_create_conversation returns same conversation for same user pair (order-independent)."""
    alice, bob = two_users
    c1 = get_or_create_conversation(alice["id"], bob["id"])
    c2 = get_or_create_conversation(bob["id"], alice["id"])
    assert c1["id"] == c2["id"]


def test_get_conversation_allowed_participant(two_users):
    """get_conversation returns the conversation when current_user is a participant."""
    alice, bob = two_users
    conv = get_or_create_conversation(alice["id"], bob["id"])
    out = get_conversation(conv["id"], alice["id"])
    assert out is not None
    assert out["id"] == conv["id"]
    out_bob = get_conversation(conv["id"], bob["id"])
    assert out_bob["id"] == conv["id"]


def test_get_conversation_forbidden_non_participant(two_users):
    """get_conversation returns None when current_user is not a participant."""
    alice, bob = two_users
    conv = get_or_create_conversation(alice["id"], bob["id"])
    charlie = _make_user("charlie", first_name="Charlie", phone="+15550100003")
    out = get_conversation(conv["id"], charlie["id"])
    assert out is None


def test_add_message_and_get_messages(two_users):
    """add_message stores a message; get_messages returns them in order (oldest last)."""
    alice, bob = two_users
    conv = get_or_create_conversation(alice["id"], bob["id"])
    m1 = add_message(conv["id"], alice["id"], "Hello Bob")
    m2 = add_message(conv["id"], bob["id"], "Hi Alice")
    assert m1["id"] is not None
    assert m1["content"] == "Hello Bob"
    assert m1["sender_id"] == alice["id"]
    messages = get_messages(conv["id"])
    assert len(messages) == 2
    assert messages[0]["content"] == "Hello Bob"
    assert messages[1]["content"] == "Hi Alice"


def test_get_messages_pagination(two_users):
    """get_messages with before_id returns older messages (oldest last)."""
    alice, bob = two_users
    conv = get_or_create_conversation(alice["id"], bob["id"])
    add_message(conv["id"], alice["id"], "First")
    m2 = add_message(conv["id"], bob["id"], "Second")
    add_message(conv["id"], alice["id"], "Third")
    # before_id=id_of_third: get messages with id < that, so First and Second, oldest last
    page = get_messages(conv["id"], limit=2, before_id=m2["id"] + 1)
    assert len(page) == 2
    assert page[0]["content"] == "First"
    assert page[1]["content"] == "Second"
    older = get_messages(conv["id"], limit=1, before_id=m2["id"])
    assert len(older) == 1
    assert older[0]["content"] == "First"


def test_get_participant_ids(two_users):
    """get_participant_ids returns both user ids for a 1:1 conversation."""
    alice, bob = two_users
    conv = get_or_create_conversation(alice["id"], bob["id"])
    ids = get_participant_ids(conv["id"])
    assert set(ids) == {alice["id"], bob["id"]}


def test_get_conversations_for_user(two_users):
    """get_conversations_for_user returns conversations with other_user and last_message."""
    alice, bob = two_users
    conv = get_or_create_conversation(alice["id"], bob["id"])
    add_message(conv["id"], alice["id"], "Hey")
    add_message(conv["id"], bob["id"], "Hi there")
    list_alice = get_conversations_for_user(alice["id"])
    assert len(list_alice) == 1
    assert list_alice[0]["id"] == conv["id"]
    assert list_alice[0]["other_user"]["id"] == bob["id"]
    assert list_alice[0]["other_user"]["username"] == "bob"
    assert list_alice[0]["last_message"] is not None
    assert list_alice[0]["last_message"]["content"] == "Hi there"


def test_get_max_message_id(two_users):
    """get_max_message_id returns latest message id or None if no messages."""
    alice, bob = two_users
    conv = get_or_create_conversation(alice["id"], bob["id"])
    assert get_max_message_id(conv["id"]) is None
    m1 = add_message(conv["id"], alice["id"], "First")
    assert get_max_message_id(conv["id"]) == m1["id"]
    m2 = add_message(conv["id"], bob["id"], "Second")
    assert get_max_message_id(conv["id"]) == m2["id"]


def test_get_unread_count_and_set_last_read(two_users):
    """get_unread_count counts messages from other after last_read; set_last_read updates state."""
    alice, bob = two_users
    conv = get_or_create_conversation(alice["id"], bob["id"])
    m1 = add_message(conv["id"], alice["id"], "Hi")
    m2 = add_message(conv["id"], bob["id"], "Hello")
    m3 = add_message(conv["id"], bob["id"], "You there?")
    assert get_unread_count(conv["id"], alice["id"]) == 2
    set_last_read(conv["id"], alice["id"], m2["id"])
    assert get_unread_count(conv["id"], alice["id"]) == 1
    set_last_read(conv["id"], alice["id"], m3["id"])
    assert get_unread_count(conv["id"], alice["id"]) == 0
