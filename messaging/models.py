"""Conversation and message model (in-app chat, no phone numbers)."""

from auth.db import get_conn


def get_or_create_conversation(user_id_1: int, user_id_2: int) -> dict:
    """Get existing 1:1 conversation between two users or create one. Returns conversation dict with id."""
    if user_id_1 > user_id_2:
        user_id_1, user_id_2 = user_id_2, user_id_1
    conn = get_conn()
    row = conn.execute(
        """SELECT c.id, c.created_at
           FROM conversations c
           JOIN conversation_participants p1 ON p1.conversation_id = c.id AND p1.user_id = ?
           JOIN conversation_participants p2 ON p2.conversation_id = c.id AND p2.user_id = ?
           LIMIT 1""",
        (user_id_1, user_id_2),
    ).fetchone()
    if row:
        return dict(row)
    conn.execute("INSERT INTO conversations DEFAULT VALUES")
    conv_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO conversation_participants (conversation_id, user_id) VALUES (?, ?), (?, ?)",
        (conv_id, user_id_1, conv_id, user_id_2),
    )
    conn.commit()
    row = conn.execute("SELECT id, created_at FROM conversations WHERE id = ?", (conv_id,)).fetchone()
    return dict(row)


def get_conversation(conversation_id: int, current_user_id: int) -> dict | None:
    """Get conversation by id if current_user is a participant."""
    conn = get_conn()
    row = conn.execute(
        """SELECT c.id, c.created_at FROM conversations c
           JOIN conversation_participants p ON p.conversation_id = c.id AND p.user_id = ?
           WHERE c.id = ?""",
        (current_user_id, conversation_id),
    ).fetchone()
    return dict(row) if row else None


def _get_conversations_for_user_sqlite(user_id: int) -> list[dict]:
    """SQLite doesn't support LATERAL; use a subquery for last message."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT c.id AS conversation_id, c.created_at,
                  other.id AS other_user_id, other.username AS other_username,
                  other.first_name AS other_first_name, other.last_name AS other_last_name
           FROM conversations c
           JOIN conversation_participants p ON p.conversation_id = c.id AND p.user_id = ?
           JOIN conversation_participants p2 ON p2.conversation_id = c.id AND p2.user_id != ?
           JOIN users other ON other.id = p2.user_id
           ORDER BY c.id DESC""",
        (user_id, user_id),
    ).fetchall()
    out = []
    for r in rows:
        last = conn.execute(
            "SELECT content, created_at FROM messages WHERE conversation_id = ? ORDER BY id DESC LIMIT 1",
            (r["conversation_id"],),
        ).fetchone()
        out.append({
            "id": r["conversation_id"],
            "created_at": r["created_at"],
            "other_user": {
                "id": r["other_user_id"],
                "username": r["other_username"],
                "first_name": r["other_first_name"],
                "last_name": r["other_last_name"],
            },
            "last_message": {"content": last["content"], "created_at": last["created_at"]} if last and last["content"] else None,
        })
    out.sort(key=lambda x: (x["last_message"] or {}).get("created_at") or "", reverse=True)
    return out


def get_conversations_for_user(user_id: int) -> list[dict]:
    """List conversations for user (SQLite-compatible)."""
    return _get_conversations_for_user_sqlite(user_id)


def get_unread_count(conversation_id: int, user_id: int) -> int:
    """Number of messages in this conversation from the other participant that the user has not read."""
    conn = get_conn()
    row = conn.execute(
        "SELECT last_read_message_id FROM conversation_read_state WHERE conversation_id = ? AND user_id = ?",
        (conversation_id, user_id),
    ).fetchone()
    last_read = (row["last_read_message_id"] or 0) if row else 0
    other_ids = [p for p in get_participant_ids(conversation_id) if p != user_id]
    if not other_ids:
        return 0
    other_id = other_ids[0]
    r = conn.execute(
        "SELECT COUNT(*) AS n FROM messages WHERE conversation_id = ? AND sender_id = ? AND id > ?",
        (conversation_id, other_id, last_read),
    ).fetchone()
    return r["n"] or 0


def set_last_read(conversation_id: int, user_id: int, message_id: int) -> None:
    """Mark conversation as read up to message_id (inclusive)."""
    conn = get_conn()
    conn.execute(
        """INSERT INTO conversation_read_state (user_id, conversation_id, last_read_message_id, updated_at)
           VALUES (?, ?, ?, datetime('now'))
           ON CONFLICT(user_id, conversation_id) DO UPDATE SET
             last_read_message_id = CASE WHEN excluded.last_read_message_id > last_read_message_id
                 THEN excluded.last_read_message_id ELSE last_read_message_id END,
             updated_at = datetime('now')""",
        (user_id, conversation_id, message_id),
    )
    conn.commit()


def add_message(conversation_id: int, sender_id: int, content: str) -> dict:
    """Append a message; return the created message dict."""
    conn = get_conn()
    conn.execute(
        "INSERT INTO messages (conversation_id, sender_id, content) VALUES (?, ?, ?)",
        (conversation_id, sender_id, content),
    )
    conn.commit()
    msg_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    row = conn.execute(
        "SELECT id, conversation_id, sender_id, content, created_at FROM messages WHERE id = ?",
        (msg_id,),
    ).fetchone()
    return dict(row)


def get_messages(conversation_id: int, limit: int = 100, before_id: int | None = None) -> list[dict]:
    """Get messages for a conversation, newest last. Optional cursor before_id for pagination."""
    conn = get_conn()
    if before_id:
        rows = conn.execute(
            """SELECT id, conversation_id, sender_id, content, created_at
               FROM messages WHERE conversation_id = ? AND id < ? ORDER BY id DESC LIMIT ?""",
            (conversation_id, before_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT id, conversation_id, sender_id, content, created_at
               FROM messages WHERE conversation_id = ? ORDER BY id DESC LIMIT ?""",
            (conversation_id, limit),
        ).fetchall()
    rows = list(reversed(rows))
    return [dict(r) for r in rows]


def get_participant_ids(conversation_id: int) -> list[int]:
    """Return user ids of all participants in the conversation."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT user_id FROM conversation_participants WHERE conversation_id = ?",
        (conversation_id,),
    ).fetchall()
    return [r["user_id"] for r in rows]


def get_max_message_id(conversation_id: int) -> int | None:
    """Return the latest message id in the conversation, or None if no messages."""
    conn = get_conn()
    row = conn.execute(
        "SELECT MAX(id) AS max_id FROM messages WHERE conversation_id = ?",
        (conversation_id,),
    ).fetchone()
    if row and row["max_id"] is not None:
        return row["max_id"]
    return None
