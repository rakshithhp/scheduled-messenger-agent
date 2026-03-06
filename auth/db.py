"""SQLite database for auth (users).

SQLite is part of Python's standard library (sqlite3) — no separate install needed.
The database file (auth.db) is created at runtime by init_db(); only the code is in git.
On AWS Elastic Beanstalk, set AUTH_DB_PATH to a persistent path if the app dir is ephemeral.
Uses thread-local connections so Flask request threads don't share one connection.
"""

import os
import sqlite3
import threading
from pathlib import Path

# Default: project root. Override with AUTH_DB_PATH (e.g. on AWS for a persistent location).
DB_DIR = Path(__file__).resolve().parent.parent
DB_PATH = os.environ.get("AUTH_DB_PATH", str(DB_DIR / "auth.db"))
_local = threading.local()


def get_conn() -> sqlite3.Connection:
    """Return a connection for the current thread (SQLite doesn't allow cross-thread use)."""
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(DB_PATH)
        _local.conn.row_factory = sqlite3.Row
    return _local.conn


def init_db() -> None:
    """Create users table if it doesn't exist; add new columns for existing DBs."""
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    for col_name, col_type in [("first_name", "TEXT"), ("last_name", "TEXT"), ("phone", "TEXT"), ("email", "TEXT")]:
        try:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
        except sqlite3.OperationalError:
            pass  # column already exists
    try:
        conn.execute("ALTER TABLE users ADD COLUMN normalized_phone TEXT")
    except sqlite3.OperationalError:
        pass
    # Backfill normalized_phone from phone for existing rows (normalize: + and digits only)
    for row in conn.execute("SELECT id, phone FROM users WHERE normalized_phone IS NULL AND phone IS NOT NULL").fetchall():
        raw = (row["phone"] or "").strip()
        if raw:
            has_plus = raw.startswith("+")
            digits = "".join(c for c in raw if c.isdigit())
            if digits:
                n = ("+" if has_plus else "") + digits
                conn.execute("UPDATE users SET normalized_phone = ? WHERE id = ?", (n, row["id"]))
    try:
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_normalized_phone ON users(normalized_phone) WHERE normalized_phone IS NOT NULL AND normalized_phone != ''")
    except sqlite3.OperationalError:
        pass

    # Messaging: conversations and messages (in-app chat, no phone)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversation_participants (
            conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id),
            PRIMARY KEY (conversation_id, user_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            sender_id INTEGER NOT NULL REFERENCES users(id),
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id)")

    # Read/unread state per user per conversation
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversation_read_state (
            user_id INTEGER NOT NULL REFERENCES users(id),
            conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            last_read_message_id INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (user_id, conversation_id)
        )
    """)

    # Rules: per-conversation, linked to user (who created the rule)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id),
            trigger TEXT NOT NULL,
            trigger_duration_seconds INTEGER,
            trigger_since_message_id INTEGER,
            action TEXT NOT NULL,
            tone TEXT,
            message_hint TEXT,
            raw_intent TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            is_active INTEGER NOT NULL DEFAULT 1
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rules_conversation ON rules(conversation_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rules_user ON rules(user_id)")

    try:
        conn.execute("ALTER TABLE rules ADD COLUMN trigger_since_message_id INTEGER")
    except sqlite3.OperationalError:
        pass

    # Drafts: agent-created message awaiting user approval
    conn.execute("""
        CREATE TABLE IF NOT EXISTS drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            rule_id INTEGER REFERENCES rules(id) ON DELETE SET NULL,
            sender_id INTEGER NOT NULL REFERENCES users(id),
            content TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            resolved_at TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_drafts_conversation ON drafts(conversation_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_drafts_sender_status ON drafts(sender_id, status)")

    # Memory layer: key moments and follow-up success tracking
    conn.execute("""
        CREATE TABLE IF NOT EXISTS key_moments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id),
            moment_type TEXT NOT NULL,
            summary TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_key_moments_conversation_user ON key_moments(conversation_id, user_id)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS follow_up_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            draft_id INTEGER REFERENCES drafts(id) ON DELETE SET NULL,
            conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            sender_id INTEGER NOT NULL REFERENCES users(id),
            sent_at TEXT NOT NULL,
            outcome TEXT NOT NULL DEFAULT 'pending',
            tone_used TEXT,
            content_preview TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_follow_up_outcomes_conversation ON follow_up_outcomes(conversation_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_follow_up_outcomes_sender ON follow_up_outcomes(sender_id)")

    # Lightweight conversation embedding cache (optional)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversation_embeddings (
            conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id),
            embedding_json TEXT,
            source_summary TEXT,
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (conversation_id, user_id)
        )
    """)

    # APNs: device tokens per user (iOS push notifications)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS device_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            device_token TEXT NOT NULL,
            platform TEXT NOT NULL DEFAULT 'ios',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE (user_id, device_token)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_device_tokens_user ON device_tokens(user_id)")

    conn.commit()
