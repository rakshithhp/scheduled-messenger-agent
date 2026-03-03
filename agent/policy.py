"""Intent → policy translation: soft constraints from natural language.

User says "Don't let this go cold" → behavioral policy the agent uses for timing and limits.
"""

import json
import os
from dataclasses import dataclass
from typing import Any

from openai import OpenAI


@dataclass
class BehavioralPolicy:
    """Soft constraints for follow-ups and timing."""

    follow_up_after_multiple_of_avg: float  # e.g. 2.0 = follow up after 2x their usual reply time
    max_follow_ups_per_period_days: float  # e.g. 1.0 = at most 1 follow-up per 3 days
    period_days: float  # e.g. 3.0
    avoid_double_text: bool  # don't send again if I was the last sender
    min_hours_between_follow_ups: float  # e.g. 72.0 = 3 days
    tone: str | None  # gentle, warm, formal, casual


POLICY_PROMPT = """You translate the user's relationship goal into a behavioral policy for an automated messaging agent.

User intent: "{raw_intent}"

Conversation state (for context):
- initiation_ratio: {initiation_ratio} (1.0 = I always start, 0.5 = even)
- avg_reply_time: {avg_reply_time} (how long they usually take to reply)
- last_sentiment: {last_sentiment}
- days_since_contact: {days_since_contact}
- conversation_frequency: {conversation_frequency} messages per day

Output a JSON object with these exact keys:
- follow_up_after_multiple_of_avg: float (e.g. 1.5 = follow up after 1.5x their average reply time; use 2.0 if "don't let go cold", higher if "give space")
- max_follow_ups_per_period_days: float (max follow-ups in the period, e.g. 1)
- period_days: float (e.g. 3.0 = "per 3 days")
- avoid_double_text: boolean (true = don't send if I was the last sender)
- min_hours_between_follow_ups: float (e.g. 72 = at least 3 days between follow-ups)
- tone: string or null ("gentle" | "warm" | "formal" | "casual" | null)

Interpretation guide:
- "Don't let this go cold" / "keep it warm" → follow_up_after_multiple_of_avg: 2, avoid_double_text: true, min_hours: 48-72
- "Not clingy" / "give space" → higher multiple (2.5), min_hours: 72, max_follow_ups: 1 per 3 days
- "Keep things warm but not clingy" → balance: follow_up after ~2x avg, max 1 per 3 days, avoid_double_text: true

Return only valid JSON, no markdown."""


def intent_to_policy(raw_intent: str, conversation_state: dict[str, Any] | None = None) -> BehavioralPolicy:
    """
    Translate user intent (e.g. "Don't let this go cold") into a behavioral policy.
    Uses conversation state when available for context-aware defaults.
    """
    state = conversation_state or {}
    prompt = POLICY_PROMPT.format(
        raw_intent=(raw_intent or "").strip() or "Keep things warm but not clingy",
        initiation_ratio=state.get("initiation_ratio", 0.5),
        avg_reply_time=state.get("avg_reply_time") or "unknown",
        last_sentiment=state.get("last_sentiment", "neutral"),
        days_since_contact=state.get("days_since_contact", 0),
        conversation_frequency=state.get("conversation_frequency", 0),
    )
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        content = (response.choices[0].message.content or "").strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()
        data = json.loads(content)
        return BehavioralPolicy(
            follow_up_after_multiple_of_avg=float(data.get("follow_up_after_multiple_of_avg", 2.0)),
            max_follow_ups_per_period_days=float(data.get("max_follow_ups_per_period_days", 1.0)),
            period_days=float(data.get("period_days", 3.0)),
            avoid_double_text=bool(data.get("avoid_double_text", True)),
            min_hours_between_follow_ups=float(data.get("min_hours_between_follow_ups", 72.0)),
            tone=data.get("tone") if data.get("tone") else None,
        )
    except Exception:
        return BehavioralPolicy(
            follow_up_after_multiple_of_avg=2.0,
            max_follow_ups_per_period_days=1.0,
            period_days=3.0,
            avoid_double_text=True,
            min_hours_between_follow_ups=72.0,
            tone="gentle",
        )


def compute_adaptive_delay_seconds(
    policy: BehavioralPolicy,
    conversation_state: dict[str, Any],
    default_fallback_seconds: int = 14400,
) -> int:
    """
    Compute follow-up delay from policy and state.
    If person normally replies in 12h, follow up at policy.follow_up_after_multiple_of_avg * 12h (e.g. 18h or 24h).
    """
    avg_seconds = conversation_state.get("avg_reply_seconds")
    if avg_seconds is not None and avg_seconds > 0:
        delay = int(policy.follow_up_after_multiple_of_avg * avg_seconds)
        min_seconds = int(policy.min_hours_between_follow_ups * 3600)
        return max(delay, min_seconds)
    return default_fallback_seconds
