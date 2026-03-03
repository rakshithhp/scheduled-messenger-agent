"""Tests for policy: BehavioralPolicy, intent_to_policy fallback, compute_adaptive_delay_seconds."""

from unittest.mock import patch
import pytest
from agent.policy import BehavioralPolicy, intent_to_policy, compute_adaptive_delay_seconds


def test_compute_adaptive_delay_uses_avg_reply_seconds():
    policy = BehavioralPolicy(2.0, 1.0, 3.0, True, 72.0, "gentle")
    state = {"avg_reply_seconds": 43200}
    delay = compute_adaptive_delay_seconds(policy, state, default_fallback_seconds=14400)
    assert delay == max(2 * 43200, 72 * 3600)


def test_compute_adaptive_delay_fallback_when_no_avg():
    policy = BehavioralPolicy(2.0, 1.0, 3.0, True, 72.0, "gentle")
    state = {}
    delay = compute_adaptive_delay_seconds(policy, state, default_fallback_seconds=14400)
    assert delay == 14400


def test_compute_adaptive_delay_respects_min_hours():
    policy = BehavioralPolicy(0.5, 1.0, 3.0, True, 24.0, None)
    state = {"avg_reply_seconds": 3600}
    delay = compute_adaptive_delay_seconds(policy, state, default_fallback_seconds=100)
    assert delay == 24 * 3600


@patch("agent.policy.OpenAI")
def test_intent_to_policy_fallback_on_exception(mock_openai):
    mock_openai.return_value.chat.completions.create.side_effect = Exception("API error")
    policy = intent_to_policy("Don't let this go cold")
    assert policy.follow_up_after_multiple_of_avg == 2.0
    assert policy.avoid_double_text is True
    assert policy.tone == "gentle"
