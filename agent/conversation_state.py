"""Conversation state: computed relationship signals from message history.

Stage 2 behavioral agent reasons with this state instead of raw chat.
"""

from datetime import datetime, timezone, timedelta
from typing import Any

from messaging.models import get_messages, get_participant_ids


def _parse_created_at(created_at: str | None) -> datetime | None:
    """Parse SQLite datetime string to naive datetime (assume UTC)."""
    if not created_at:
        return None
    try:
        if isinstance(created_at, datetime):
            return created_at
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
            try:
                return datetime.strptime(created_at.strip()[:19], fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None
    except Exception:
        return None


def _simple_sentiment(content: str) -> str:
    """Simple heuristic sentiment. Returns 'positive' | 'neutral' | 'negative'."""
    if not content:
        return "neutral"
    lower = content.lower()
    positive = ("thanks", "thank", "love", "great", "happy", "yes", "ok", "okay", "sure", "❤", "😊", "👍")
    negative = ("no", "don't", "won't", "sorry", "bad", "angry", "upset", "sad", "😞")
    if any(p in lower for p in positive) and not any(n in lower for n in negative):
        return "positive"
    if any(n in lower for n in negative):
        return "negative"
    return "neutral"


def get_conversation_state(conversation_id: int, current_user_id: int) -> dict[str, Any]:
    """
    Compute relationship signals for this conversation from the perspective of current_user_id.

    Returns a dict suitable for the behavioral agent, e.g.:
    {
      "initiation_ratio": 0.8,
      "avg_reply_seconds": 50400,
      "avg_reply_time": "14h",
      "last_sentiment": "neutral",
      "last_5_sentiment": ["neutral", "positive", ...],
      "unanswered_messages": 1,
      "days_since_contact": 5.2,
      "conversation_frequency": 2.1,
      "message_count": 42,
    }
    """
    participants = get_participant_ids(conversation_id)
    other_id = next((x for x in participants if x != current_user_id), None)
    if not other_id:
        return _empty_state()

    messages = get_messages(conversation_id, limit=500)
    if not messages:
        return _empty_state()

    now = datetime.now(timezone.utc)
    gap_threshold_seconds = 12 * 3600  # 12h = new "thread" for initiation count

    my_initiations = 0
    their_initiations = 0
    reply_deltas: list[float] = []  # seconds from their message to my reply
    last_ts: datetime | None = None
    last_sender: int | None = None
    unanswered = 0
    last_five_sentiments: list[str] = []
    message_timestamps: list[datetime] = []

    for m in messages:
        ts = _parse_created_at(m.get("created_at"))
        sender = m.get("sender_id")
        if ts is None:
            continue
        message_timestamps.append(ts)
        last_five_sentiments.append(_simple_sentiment(m.get("content") or ""))
        if len(last_five_sentiments) > 5:
            last_five_sentiments.pop(0)

        # Initiation: first message after a long gap or start
        if last_ts is None or (ts - last_ts).total_seconds() > gap_threshold_seconds:
            if sender == current_user_id:
                my_initiations += 1
            else:
                their_initiations += 1

        # Reply latency: they sent, then I replied
        if last_sender == other_id and sender == current_user_id and last_ts:
            reply_deltas.append((ts - last_ts).total_seconds())

        last_ts = ts
        last_sender = sender

    # Unanswered: trailing messages from the other without a reply from me
    if messages:
        for m in reversed(messages):
            if m.get("sender_id") == current_user_id:
                break
            if m.get("sender_id") == other_id:
                unanswered += 1
    total_initiations = my_initiations + their_initiations
    initiation_ratio = (my_initiations / total_initiations) if total_initiations else 0.5

    avg_reply_seconds = (sum(reply_deltas) / len(reply_deltas)) if reply_deltas else None
    if avg_reply_seconds is not None and avg_reply_seconds < 0:
        avg_reply_seconds = None

    def _format_duration(sec: float) -> str:
        if sec < 60:
            return f"{int(sec)}s"
        if sec < 3600:
            return f"{int(sec / 60)}m"
        if sec < 86400:
            return f"{round(sec / 3600, 1)}h"
        return f"{round(sec / 86400, 1)}d"

    days_since_contact = 0.0
    if message_timestamps:
        last_contact = max(message_timestamps)
        days_since_contact = (now - last_contact).total_seconds() / 86400.0

    window_start = now - timedelta(days=30)
    messages_in_window = sum(1 for t in message_timestamps if t >= window_start)
    conversation_frequency = messages_in_window / 30.0 if messages_in_window else 0.0

    last_sentiment = last_five_sentiments[-1] if last_five_sentiments else "neutral"

    return {
        "initiation_ratio": round(initiation_ratio, 2),
        "avg_reply_seconds": int(avg_reply_seconds) if avg_reply_seconds is not None else None,
        "avg_reply_time": _format_duration(avg_reply_seconds) if avg_reply_seconds is not None else None,
        "last_sentiment": last_sentiment,
        "last_5_sentiment": last_five_sentiments[-5:] if len(last_five_sentiments) >= 5 else last_five_sentiments,
        "unanswered_messages": unanswered,
        "days_since_contact": round(days_since_contact, 1),
        "conversation_frequency": round(conversation_frequency, 2),
        "message_count": len(messages),
    }


def _empty_state() -> dict[str, Any]:
    return {
        "initiation_ratio": 0.5,
        "avg_reply_seconds": None,
        "avg_reply_time": None,
        "last_sentiment": "neutral",
        "last_5_sentiment": [],
        "unanswered_messages": 0,
        "days_since_contact": 0.0,
        "conversation_frequency": 0.0,
        "message_count": 0,
    }
