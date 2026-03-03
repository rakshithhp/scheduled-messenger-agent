"""Tests for agent worker helpers (_recipient_replied_since, _i_sent_after)."""

import pytest
from auth.models import create_user, get_user_by_username
from messaging.models import get_or_create_conversation, add_message
from agent.worker import _recipient_replied_since, _i_sent_after


def _user(username):
    create_user(username, "pass")
    return get_user_by_username(username)


@pytest.fixture
def conv_and_users():
    alice, bob = _user("alice"), _user("bob")
    conv = get_or_create_conversation(alice["id"], bob["id"])
    return conv, alice, bob


def test_recipient_replied_since_false_when_no_messages_after(conv_and_users):
    conv, alice, bob = conv_and_users
    m1 = add_message(conv["id"], alice["id"], "Hi")
    add_message(conv["id"], bob["id"], "Hello")
    assert _recipient_replied_since(conv["id"], alice["id"], m1["id"]) is True
    m2 = add_message(conv["id"], alice["id"], "How are you?")
    assert _recipient_replied_since(conv["id"], alice["id"], m2["id"]) is False


def test_recipient_replied_since_true_when_recipient_sent_after(conv_and_users):
    conv, alice, bob = conv_and_users
    m1 = add_message(conv["id"], alice["id"], "Hi")
    add_message(conv["id"], bob["id"], "Reply")
    assert _recipient_replied_since(conv["id"], alice["id"], m1["id"]) is True


def test_i_sent_after_false_when_only_recipient_sent_after(conv_and_users):
    conv, alice, bob = conv_and_users
    m1 = add_message(conv["id"], alice["id"], "Hi")
    add_message(conv["id"], bob["id"], "Reply")
    assert _i_sent_after(conv["id"], alice["id"], m1["id"]) is False


def test_i_sent_after_true_when_i_sent_after(conv_and_users):
    conv, alice, bob = conv_and_users
    m1 = add_message(conv["id"], alice["id"], "Hi")
    add_message(conv["id"], alice["id"], "Follow-up")
    assert _i_sent_after(conv["id"], alice["id"], m1["id"]) is True
