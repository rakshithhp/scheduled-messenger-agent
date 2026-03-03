"""Memory layer: key moments, follow-up success tracking, optional conversation embeddings.

Agent can reason: "Last 2 follow-ups worked when short and playful" and adapt tone.
"""

import json
from datetime import datetime, timezone
from typing import Any

from auth.db import get_conn
from messaging.models import get_participant_ids


def record_key_moment(
    conversation_id: int,
    user_id: int,
    moment_type: str,
    summary: str | None = None,
) -> dict:
    """Record a key moment (e.g. follow_up_sent, reply_after_follow_up, no_reply_after_follow_up)."""
    conn = get_conn()
    conn.execute(
        """INSERT INTO key_moments (conversation_id, user_id, moment_type, summary)
           VALUES (?, ?, ?, ?)""",
        (conversation_id, user_id, moment_type, summary or ""),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM key_moments WHERE id = last_insert_rowid()").fetchone()
    return dict(row)


def get_recent_key_moments(
    conversation_id: int,
    user_id: int,
    limit: int = 10,
) -> list[dict]:
    """Get recent key moments for this conversation from this user's perspective."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT id, conversation_id, user_id, moment_type, summary, created_at
           FROM key_moments
           WHERE conversation_id = ? AND user_id = ?
           ORDER BY id DESC LIMIT ?""",
        (conversation_id, user_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def record_follow_up_sent(
    conversation_id: int,
    sender_id: int,
    content_preview: str | None = None,
    tone_used: str | None = None,
    draft_id: int | None = None,
) -> dict:
    """Record that a follow-up was sent (draft approved or auto-sent). Outcome starts as pending."""
    conn = get_conn()
    sent_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """INSERT INTO follow_up_outcomes (draft_id, conversation_id, sender_id, sent_at, outcome, tone_used, content_preview)
           VALUES (?, ?, ?, ?, 'pending', ?, ?)""",
        (draft_id, conversation_id, sender_id, sent_at, tone_used or "", (content_preview or "")[:200]),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM follow_up_outcomes WHERE id = last_insert_rowid()").fetchone()
    return dict(row)


def mark_follow_up_led_to_reply(conversation_id: int, follow_up_sender_id: int) -> int:
    """
    When the recipient sends a message, mark the most recent pending follow-up from the other side as led_to_reply.
    Returns the number of rows updated (0 or 1).
    """
    conn = get_conn()
    row = conn.execute(
        """SELECT id FROM follow_up_outcomes
           WHERE conversation_id = ? AND sender_id = ? AND outcome = 'pending'
           ORDER BY id DESC LIMIT 1""",
        (conversation_id, follow_up_sender_id),
    ).fetchone()
    if not row:
        return 0
    conn.execute("UPDATE follow_up_outcomes SET outcome = 'led_to_reply' WHERE id = ?", (row["id"],))
    conn.commit()
    return 1


def mark_pending_follow_ups_no_reply(conversation_id: int, sender_id: int) -> int:
    """Mark all pending follow-ups for this conversation/sender as no_reply (e.g. before sending a new one)."""
    conn = get_conn()
    conn.execute(
        "UPDATE follow_up_outcomes SET outcome = 'no_reply' WHERE conversation_id = ? AND sender_id = ? AND outcome = 'pending'",
        (conversation_id, sender_id),
    )
    conn.commit()
    return conn.total_changes


def get_follow_up_outcomes(
    conversation_id: int,
    sender_id: int,
    limit: int = 10,
) -> list[dict]:
    """Get recent follow-up outcomes for this conversation (sender = user who sent follow-ups)."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT id, draft_id, conversation_id, sender_id, sent_at, outcome, tone_used, content_preview, created_at
           FROM follow_up_outcomes
           WHERE conversation_id = ? AND sender_id = ?
           ORDER BY id DESC LIMIT ?""",
        (conversation_id, sender_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def get_follow_up_success_summary(conversation_id: int, sender_id: int, last_n: int = 5) -> str:
    """
    Build a short summary for the agent, e.g. "Last 2 follow-ups led to reply when short and playful."
    Used to adapt tone in generate_followup_draft.
    """
    outcomes = get_follow_up_outcomes(conversation_id, sender_id, limit=last_n)
    if not outcomes:
        return ""
    led_to_reply = [o for o in outcomes if o.get("outcome") == "led_to_reply"]
    no_reply = [o for o in outcomes if o.get("outcome") == "no_reply"]
    pending = [o for o in outcomes if o.get("outcome") == "pending"]
    if not led_to_reply and not no_reply:
        return ""
    tones = [o.get("tone_used") or "unknown" for o in outcomes if o.get("tone_used")]
    tone_note = f" (tone: {tones[0]})" if tones else ""
    if led_to_reply:
        return f"Last {len(led_to_reply)} follow-up(s) led to reply{tone_note}. Prefer similar style."
    if no_reply:
        return f"Last follow-up(s) got no reply{tone_note}. Try a different tone or wait longer."
    return ""


def update_conversation_embedding(
    conversation_id: int,
    user_id: int,
    embedding_json: str,
    source_summary: str | None = None,
) -> None:
    """Store or update lightweight conversation embedding (e.g. from last N messages)."""
    conn = get_conn()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """INSERT OR REPLACE INTO conversation_embeddings (conversation_id, user_id, embedding_json, source_summary, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        (conversation_id, user_id, embedding_json, source_summary or "", now),
    )
    conn.commit()


def get_conversation_embedding(conversation_id: int, user_id: int) -> dict | None:
    """Get cached conversation embedding if any."""
    conn = get_conn()
    row = conn.execute(
        "SELECT embedding_json, source_summary, updated_at FROM conversation_embeddings WHERE conversation_id = ? AND user_id = ?",
        (conversation_id, user_id),
    ).fetchone()
    if not row:
        return None
    row = dict(row)
    try:
        emb = json.loads(row["embedding_json"]) if row.get("embedding_json") else None
    except Exception:
        emb = None
    return {
        "embedding": emb,
        "source_summary": row.get("source_summary"),
        "updated_at": row.get("updated_at"),
    }
