"""Rule and draft storage. Rules are per-conversation and linked to the user who created them."""

from auth.db import get_conn


def create_rule(
    conversation_id: int,
    user_id: int,
    *,
    trigger: str,
    trigger_duration_seconds: int | None = None,
    trigger_since_message_id: int | None = None,
    action: str = "send_exact",
    tone: str | None = None,
    message_hint: str | None = None,
    raw_intent: str | None = None,
) -> dict:
    """Create a rule for a conversation. Returns the rule dict."""
    conn = get_conn()
    conn.execute(
        """INSERT INTO rules (conversation_id, user_id, trigger, trigger_duration_seconds, trigger_since_message_id, action, tone, message_hint, raw_intent)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            conversation_id,
            user_id,
            trigger,
            trigger_duration_seconds,
            trigger_since_message_id,
            action,
            tone,
            message_hint or None,
            raw_intent or None,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM rules WHERE id = last_insert_rowid()").fetchone()
    return dict(row)


def get_rules_for_conversation(conversation_id: int, active_only: bool = True) -> list[dict]:
    """Return rules for a conversation, optionally only active."""
    conn = get_conn()
    if active_only:
        rows = conn.execute(
            "SELECT * FROM rules WHERE conversation_id = ? AND is_active = 1 ORDER BY id DESC",
            (conversation_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM rules WHERE conversation_id = ? ORDER BY id DESC",
            (conversation_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_rules_for_user(user_id: int, active_only: bool = True) -> list[dict]:
    """Return rules created by a user across all conversations."""
    conn = get_conn()
    if active_only:
        rows = conn.execute(
            "SELECT * FROM rules WHERE user_id = ? AND is_active = 1 ORDER BY id DESC",
            (user_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM rules WHERE user_id = ? ORDER BY id DESC",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_rule(rule_id: int, user_id: int | None = None) -> dict | None:
    """Get a rule by id. Optionally require user_id to match."""
    conn = get_conn()
    if user_id is not None:
        row = conn.execute(
            "SELECT * FROM rules WHERE id = ? AND user_id = ?",
            (rule_id, user_id),
        ).fetchone()
    else:
        row = conn.execute("SELECT * FROM rules WHERE id = ?", (rule_id,)).fetchone()
    return dict(row) if row else None


def deactivate_rule(rule_id: int, user_id: int) -> bool:
    """Set rule is_active = 0. Returns True if updated."""
    conn = get_conn()
    conn.execute("UPDATE rules SET is_active = 0 WHERE id = ? AND user_id = ?", (rule_id, user_id))
    conn.commit()
    return conn.total_changes > 0


# Drafts
def create_draft(
    conversation_id: int,
    sender_id: int,
    content: str,
    *,
    rule_id: int | None = None,
) -> dict:
    """Create a pending draft (agent-generated message awaiting approval)."""
    conn = get_conn()
    conn.execute(
        """INSERT INTO drafts (conversation_id, rule_id, sender_id, content, status)
           VALUES (?, ?, ?, ?, 'pending')""",
        (conversation_id, rule_id, sender_id, content),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM drafts WHERE id = last_insert_rowid()").fetchone()
    return dict(row)


def get_pending_drafts_for_user(user_id: int) -> list[dict]:
    """Return pending drafts where user is the sender (they need to approve)."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM drafts WHERE sender_id = ? AND status = 'pending' ORDER BY id DESC",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_pending_drafts_for_conversation(conversation_id: int, sender_id: int) -> list[dict]:
    """Return pending drafts for a conversation for the given sender."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM drafts WHERE conversation_id = ? AND sender_id = ? AND status = 'pending' ORDER BY id DESC",
        (conversation_id, sender_id),
    ).fetchall()
    return [dict(r) for r in rows]


def get_draft(draft_id: int, sender_id: int) -> dict | None:
    """Get a draft by id. Must belong to sender_id."""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM drafts WHERE id = ? AND sender_id = ?",
        (draft_id, sender_id),
    ).fetchone()
    return dict(row) if row else None


def resolve_draft(draft_id: int, sender_id: int, status: str) -> dict | None:
    """Set draft status to 'approved' or 'rejected' and set resolved_at. Returns draft or None."""
    conn = get_conn()
    if status not in ("approved", "rejected"):
        return None
    conn.execute(
        "UPDATE drafts SET status = ?, resolved_at = datetime('now') WHERE id = ? AND sender_id = ? AND status = 'pending'",
        (status, draft_id, sender_id),
    )
    conn.commit()
    if conn.total_changes == 0:
        return None
    row = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    return dict(row) if row else None


def resolve_pending_reply_suggestions(conversation_id: int, sender_id: int) -> int:
    """Reject all pending reply-suggestion drafts (rule_id IS NULL) for this conversation and sender. Returns count updated."""
    conn = get_conn()
    conn.execute(
        """UPDATE drafts SET status = 'rejected', resolved_at = datetime('now')
           WHERE conversation_id = ? AND sender_id = ? AND status = 'pending' AND rule_id IS NULL""",
        (conversation_id, sender_id),
    )
    conn.commit()
    return conn.total_changes
