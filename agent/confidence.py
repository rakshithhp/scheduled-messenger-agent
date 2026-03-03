"""Confidence scoring, risk evaluation, and frequency caps for autonomy decisions.

If confidence high + risk low + within cap → auto-send.
If medium → ask approval (draft).
If low → do nothing.
"""

import json
import os
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from agent.memory import get_follow_up_outcomes
from agent.conversation_state import get_conversation_state


@dataclass
class ConfidenceResult:
    score: float  # 0–1
    risk_level: str  # "low" | "medium" | "high"
    within_frequency_cap: bool
    reason: str


# Max follow-ups per 7 days per conversation (frequency cap)
DEFAULT_FOLLOW_UPS_PER_WEEK = 2


def _follow_ups_in_last_n_days(conversation_id: int, sender_id: int, days: int = 7) -> int:
    """Count follow-ups (sent, any outcome) in the last N days."""
    from auth.db import get_conn
    conn = get_conn()
    modifier = f"-{days} days"
    rows = conn.execute(
        """SELECT id FROM follow_up_outcomes
           WHERE conversation_id = ? AND sender_id = ?
           AND datetime(created_at) >= datetime('now', ?)""",
        (conversation_id, sender_id, modifier),
    ).fetchall()
    return len(rows)


def compute_confidence(
    conversation_id: int,
    user_id: int,
    rule: dict | None = None,
    conversation_state: dict[str, Any] | None = None,
    memory_summary: str | None = None,
    *,
    follow_ups_per_week_cap: int = DEFAULT_FOLLOW_UPS_PER_WEEK,
) -> ConfidenceResult:
    """
    Compute confidence score, risk level, and whether we're within frequency cap.
    Uses conversation state and past follow-up outcomes when available.
    """
    state = conversation_state or get_conversation_state(conversation_id, user_id)
    outcomes = get_follow_up_outcomes(conversation_id, user_id, limit=10)
    follow_ups_recent = _follow_ups_in_last_n_days(conversation_id, user_id, days=7)
    within_cap = follow_ups_recent < follow_ups_per_week_cap

    # Heuristic: high confidence if recent follow-ups led to reply and we're within cap
    success_count = sum(1 for o in outcomes if o.get("outcome") == "led_to_reply")
    recent_success = success_count > 0 and len(outcomes) <= 5
    low_activity = (state.get("message_count") or 0) < 3
    high_unanswered = (state.get("unanswered_messages") or 0) >= 2

    # Risk: higher if we've had no success, or conversation is cold, or many unanswered
    if high_unanswered or (len(outcomes) >= 2 and success_count == 0):
        risk = "high"
        reason = "Past follow-ups had no reply or multiple unanswered; higher risk."
    elif low_activity or (state.get("days_since_contact") or 0) > 7:
        risk = "medium"
        reason = "Low activity or long gap; medium risk."
    else:
        risk = "low"
        reason = "Recent success or healthy engagement; lower risk."

    # Optional: LLM-based confidence for richer reasoning
    try:
        score, risk_override, reason_override = _llm_confidence(
            state=state,
            outcomes=outcomes,
            memory_summary=memory_summary or "",
            within_cap=within_cap,
        )
        if score is not None:
            return ConfidenceResult(
                score=score,
                risk_level=risk_override or risk,
                within_frequency_cap=within_cap,
                reason=reason_override or reason,
            )
    except Exception:
        pass

    # Fallback heuristic score
    if risk == "high":
        score = 0.2
    elif risk == "medium":
        score = 0.5
    else:
        score = 0.7 if recent_success else 0.5
    if not within_cap:
        score = min(score, 0.3)
    return ConfidenceResult(score=score, risk_level=risk, within_frequency_cap=within_cap, reason=reason)


def _llm_confidence(
    state: dict,
    outcomes: list[dict],
    memory_summary: str,
    within_cap: bool,
) -> tuple[float | None, str | None, str | None]:
    """Optional LLM pass for confidence and risk. Returns (score, risk_level, reason) or (None, None, None)."""
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    prompt = f"""Given this conversation state and follow-up history, output a single JSON object:
- confidence_score: float 0 to 1 (1 = very safe to auto-send a follow-up, 0 = do not send)
- risk_level: "low" | "medium" | "high"
- reason: one short sentence

State: initiation_ratio={state.get('initiation_ratio')}, avg_reply_time={state.get('avg_reply_time')}, days_since_contact={state.get('days_since_contact')}, unanswered_messages={state.get('unanswered_messages')}
Memory: {memory_summary or 'None'}
Recent follow-up outcomes: {json.dumps([o.get('outcome') for o in outcomes[:5]])}
Within frequency cap: {within_cap}

Consider: past success → higher confidence; no reply to recent follow-ups → lower; cold conversation → medium. Output only JSON."""
    try:
        resp = client.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}], temperature=0.1)
        content = (resp.choices[0].message.content or "").strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()
        data = json.loads(content)
        score = float(data.get("confidence_score", 0.5))
        score = max(0.0, min(1.0, score))
        risk = data.get("risk_level") or "medium"
        if risk not in ("low", "medium", "high"):
            risk = "medium"
        return (score, risk, data.get("reason") or "")
    except Exception:
        return (None, None, None)


def should_auto_send(result: ConfidenceResult, *, high_threshold: float = 0.75) -> bool:
    """True if we should auto-send (no approval)."""
    return (
        result.score >= high_threshold
        and result.risk_level == "low"
        and result.within_frequency_cap
    )


def should_ask_approval(result: ConfidenceResult, *, low_threshold: float = 0.35) -> bool:
    """True if we should create a draft and ask for approval."""
    return low_threshold <= result.score < 0.75 and result.within_frequency_cap


def should_do_nothing(result: ConfidenceResult, *, low_threshold: float = 0.35) -> bool:
    """True if we should not send and not suggest (do nothing)."""
    return result.score < low_threshold or not result.within_frequency_cap
