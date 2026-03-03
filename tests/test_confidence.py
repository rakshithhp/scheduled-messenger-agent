"""Tests for confidence scoring (agent/confidence.py)."""

import pytest

from auth.models import create_user, get_user_by_username
from messaging.models import get_or_create_conversation, add_message

from agent.conversation_state import get_conversation_state
from agent.memory import record_follow_up_sent, record_key_moment
from agent.confidence import (
    ConfidenceResult,
    compute_confidence,
    should_auto_send,
    should_ask_approval,
    should_do_nothing,
)


def _user(username: str):
    create_user(username, "pass")
    return get_user_by_username(username)


@pytest.fixture
def conv_and_users():
    alice = _user("alice")
    bob = _user("bob")
    conv = get_or_create_conversation(alice["id"], bob["id"])
    return conv, alice, bob


def test_compute_confidence_returns_result(conv_and_users):
    """compute_confidence returns ConfidenceResult with score, risk_level, within_frequency_cap."""
    conv, alice, bob = conv_and_users
    add_message(conv["id"], alice["id"], "Hi")
    add_message(conv["id"], bob["id"], "Hello")
    state = get_conversation_state(conv["id"], alice["id"])
    result = compute_confidence(conv["id"], alice["id"], conversation_state=state)
    assert isinstance(result, ConfidenceResult)
    assert 0 <= result.score <= 1
    assert result.risk_level in ("low", "medium", "high")
    assert isinstance(result.within_frequency_cap, bool)
    assert isinstance(result.reason, str)


def test_should_auto_send_requires_high_score_and_low_risk():
    """should_auto_send is True only when score >= 0.75, risk low, within cap."""
    assert should_auto_send(ConfidenceResult(0.8, "low", True, "")) is True
    assert should_auto_send(ConfidenceResult(0.5, "low", True, "")) is False
    assert should_auto_send(ConfidenceResult(0.8, "high", True, "")) is False
    assert should_auto_send(ConfidenceResult(0.8, "low", False, "")) is False


def test_should_ask_approval_medium_range():
    """should_ask_approval is True for medium score and within cap."""
    assert should_ask_approval(ConfidenceResult(0.5, "medium", True, "")) is True
    assert should_ask_approval(ConfidenceResult(0.2, "high", True, "")) is False
    assert should_ask_approval(ConfidenceResult(0.5, "medium", False, "")) is False


def test_should_do_nothing_low_score_or_over_cap():
    """should_do_nothing is True when score < 0.35 or not within cap."""
    assert should_do_nothing(ConfidenceResult(0.2, "high", True, "")) is True
    assert should_do_nothing(ConfidenceResult(0.5, "medium", False, "")) is True
    assert should_do_nothing(ConfidenceResult(0.5, "medium", True, "")) is False
    assert should_do_nothing(ConfidenceResult(0.8, "low", True, "")) is False


def test_within_frequency_cap_after_follow_ups(conv_and_users):
    """When follow_ups in last 7 days >= cap, within_frequency_cap is False (heuristic path)."""
    conv, alice, bob = conv_and_users
    for _ in range(3):
        record_follow_up_sent(conv["id"], alice["id"], "Hi", None, None)
    result = compute_confidence(conv["id"], alice["id"], follow_ups_per_week_cap=2)
    assert result.within_frequency_cap is False
