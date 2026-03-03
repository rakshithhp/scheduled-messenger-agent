"""Tests for rules and drafts (agent/rules.py)."""

import pytest

from auth.models import create_user
from auth.models import get_user_by_username
from messaging.models import get_or_create_conversation, add_message

from agent.rules import (
    create_rule,
    get_rules_for_conversation,
    get_rules_for_user,
    get_rule,
    deactivate_rule,
    create_draft,
    get_pending_drafts_for_user,
    get_pending_drafts_for_conversation,
    get_draft,
    resolve_draft,
    resolve_pending_reply_suggestions,
)


def _user(username: str):
    create_user(username, "pass")
    return get_user_by_username(username)


@pytest.fixture
def conv_two_users():
    a, b = _user("alice"), _user("bob")
    c = get_or_create_conversation(a["id"], b["id"])
    return c, a, b


def test_create_rule_and_get_rule(conv_two_users):
    """create_rule stores a rule; get_rule returns it."""
    conv, alice, bob = conv_two_users
    r = create_rule(
        conv["id"],
        alice["id"],
        trigger="no_reply",
        trigger_duration_seconds=14400,
        trigger_since_message_id=10,
        action="generate_followup",
        tone="gentle",
        message_hint="follow up",
    )
    assert r["id"] is not None
    assert r["conversation_id"] == conv["id"]
    assert r["user_id"] == alice["id"]
    assert r["trigger"] == "no_reply"
    assert r["trigger_duration_seconds"] == 14400
    assert r["trigger_since_message_id"] == 10
    assert r["is_active"] == 1
    got = get_rule(r["id"])
    assert got is not None
    assert got["id"] == r["id"]


def test_get_rule_with_user_id_filter(conv_two_users):
    """get_rule with user_id returns only if owner matches."""
    conv, alice, bob = conv_two_users
    r = create_rule(conv["id"], alice["id"], trigger="no_reply", trigger_duration_seconds=3600)
    assert get_rule(r["id"], user_id=alice["id"]) is not None
    assert get_rule(r["id"], user_id=bob["id"]) is None


def test_get_rules_for_conversation(conv_two_users):
    """get_rules_for_conversation returns only that conversation's rules."""
    conv, alice, bob = conv_two_users
    create_rule(conv["id"], alice["id"], trigger="no_reply", trigger_duration_seconds=3600)
    list_r = get_rules_for_conversation(conv["id"])
    assert len(list_r) == 1
    assert list_r[0]["trigger"] == "no_reply"


def test_get_rules_for_user(conv_two_users):
    """get_rules_for_user returns rules created by that user."""
    conv, alice, bob = conv_two_users
    create_rule(conv["id"], alice["id"], trigger="no_reply", trigger_duration_seconds=3600)
    assert len(get_rules_for_user(alice["id"])) == 1
    assert len(get_rules_for_user(bob["id"])) == 0


def test_deactivate_rule(conv_two_users):
    """deactivate_rule sets is_active=0; active_only list excludes it."""
    conv, alice, bob = conv_two_users
    r = create_rule(conv["id"], alice["id"], trigger="no_reply", trigger_duration_seconds=3600)
    assert deactivate_rule(r["id"], alice["id"]) is True
    assert get_rules_for_conversation(conv["id"], active_only=True) == []
    assert len(get_rules_for_conversation(conv["id"], active_only=False)) == 1


def test_create_draft_and_get_draft(conv_two_users):
    """create_draft stores a draft; get_draft returns it for the sender."""
    conv, alice, bob = conv_two_users
    d = create_draft(conv["id"], alice["id"], "Hello back!", rule_id=None)
    assert d["id"] is not None
    assert d["status"] == "pending"
    assert d["content"] == "Hello back!"
    assert get_draft(d["id"], alice["id"]) is not None
    assert get_draft(d["id"], bob["id"]) is None


def test_get_pending_drafts_for_user(conv_two_users):
    """get_pending_drafts_for_user returns only pending drafts for that sender."""
    conv, alice, bob = conv_two_users
    create_draft(conv["id"], alice["id"], "Draft 1")
    create_draft(conv["id"], bob["id"], "Draft 2")
    alice_list = get_pending_drafts_for_user(alice["id"])
    assert len(alice_list) == 1
    assert alice_list[0]["content"] == "Draft 1"


def test_resolve_draft_approved(conv_two_users):
    """resolve_draft with 'approved' updates status and returns draft."""
    conv, alice, bob = conv_two_users
    d = create_draft(conv["id"], alice["id"], "Hi")
    out = resolve_draft(d["id"], alice["id"], "approved")
    assert out is not None
    assert out["status"] == "approved"
    assert get_draft(d["id"], alice["id"])["status"] == "approved"
    assert get_pending_drafts_for_user(alice["id"]) == []


def test_resolve_draft_rejected(conv_two_users):
    """resolve_draft with 'rejected' sets status to rejected."""
    conv, alice, bob = conv_two_users
    d = create_draft(conv["id"], alice["id"], "Hi")
    resolve_draft(d["id"], alice["id"], "rejected")
    assert get_draft(d["id"], alice["id"])["status"] == "rejected"


def test_resolve_draft_invalid_status_returns_none(conv_two_users):
    """resolve_draft with invalid status returns None."""
    conv, alice, bob = conv_two_users
    d = create_draft(conv["id"], alice["id"], "Hi")
    assert resolve_draft(d["id"], alice["id"], "invalid") is None


def test_resolve_pending_reply_suggestions(conv_two_users):
    """resolve_pending_reply_suggestions rejects only pending reply-suggestion drafts (rule_id NULL)."""
    conv, alice, bob = conv_two_users
    d1 = create_draft(conv["id"], alice["id"], "Reply suggestion", rule_id=None)
    d2 = create_draft(conv["id"], alice["id"], "Follow-up draft", rule_id=999)
    resolve_pending_reply_suggestions(conv["id"], alice["id"])
    assert get_draft(d1["id"], alice["id"])["status"] == "rejected"
    assert get_draft(d2["id"], alice["id"])["status"] == "pending"
