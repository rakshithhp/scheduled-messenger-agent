"""Tests for memory layer (agent/memory.py)."""

import pytest
from auth.models import create_user, get_user_by_username
from messaging.models import get_or_create_conversation
from agent.memory import (
    record_key_moment,
    get_recent_key_moments,
    record_follow_up_sent,
    mark_follow_up_led_to_reply,
    mark_pending_follow_ups_no_reply,
    get_follow_up_outcomes,
    get_follow_up_success_summary,
    update_conversation_embedding,
    get_conversation_embedding,
)


def _user(username):
    create_user(username, "pass")
    return get_user_by_username(username)


@pytest.fixture
def conv_and_users():
    alice, bob = _user("alice"), _user("bob")
    conv = get_or_create_conversation(alice["id"], bob["id"])
    return conv, alice, bob


def test_record_key_moment_and_get_recent(conv_and_users):
    conv, alice, bob = conv_and_users
    record_key_moment(conv["id"], alice["id"], "follow_up_sent", "Sent a follow-up")
    record_key_moment(conv["id"], alice["id"], "reply_after_follow_up", "They replied")
    moments = get_recent_key_moments(conv["id"], alice["id"], limit=10)
    assert len(moments) == 2
    assert moments[0]["moment_type"] == "reply_after_follow_up"


def test_record_follow_up_sent_and_outcomes(conv_and_users):
    conv, alice, bob = conv_and_users
    record_follow_up_sent(conv["id"], alice["id"], "Just checking in", "gentle", None)
    outcomes = get_follow_up_outcomes(conv["id"], alice["id"])
    assert len(outcomes) == 1
    assert outcomes[0]["outcome"] == "pending"


def test_mark_follow_up_led_to_reply(conv_and_users):
    conv, alice, bob = conv_and_users
    record_follow_up_sent(conv["id"], alice["id"], "Hi", "gentle", None)
    n = mark_follow_up_led_to_reply(conv["id"], alice["id"])
    assert n == 1
    outcomes = get_follow_up_outcomes(conv["id"], alice["id"])
    assert outcomes[0]["outcome"] == "led_to_reply"


def test_mark_pending_follow_ups_no_reply(conv_and_users):
    conv, alice, bob = conv_and_users
    record_follow_up_sent(conv["id"], alice["id"], "Hi", None, None)
    mark_pending_follow_ups_no_reply(conv["id"], alice["id"])
    outcomes = get_follow_up_outcomes(conv["id"], alice["id"])
    assert len(outcomes) == 1
    assert outcomes[0]["outcome"] == "no_reply"


def test_get_follow_up_success_summary_empty(conv_and_users):
    conv, alice, bob = conv_and_users
    assert get_follow_up_success_summary(conv["id"], alice["id"]) == ""


def test_conversation_embedding_roundtrip(conv_and_users):
    conv, alice, bob = conv_and_users
    update_conversation_embedding(conv["id"], alice["id"], "[0.1, 0.2]", "last 5")
    got = get_conversation_embedding(conv["id"], alice["id"])
    assert got is not None
    assert got["source_summary"] == "last 5"
