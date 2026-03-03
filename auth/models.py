"""User model and storage.

Phone is the stable unique identifier for messaging; user_id and first_name can vary.
Phone is stored normalized (E.164-like: digits and optional leading +) for uniqueness.
"""

import re
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

from auth.db import get_conn


def normalize_phone(phone: str | None) -> str | None:
    """Normalize for storage and lookup: optional leading +, then digits only. Empty -> None."""
    if not phone or not (s := phone.strip()):
        return None
    has_plus = s.startswith("+")
    digits = re.sub(r"\D", "", s)
    if not digits:
        return None
    return ("+" if has_plus else "") + digits


def create_user(
    username: str,
    password: str,
    *,
    first_name: str | None = None,
    last_name: str | None = None,
    phone: str | None = None,
    email: str | None = None,
) -> dict | None:
    """Create a user. Returns user dict or None if username taken."""
    username = username.strip().lower()
    if not username or not password:
        return None
    password_hash = generate_password_hash(password, method="scrypt")
    phone_normalized = normalize_phone(phone) if phone else None
    conn = get_conn()
    try:
        cursor = conn.execute(
            """INSERT INTO users (username, password_hash, first_name, last_name, phone, normalized_phone, email)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                username,
                password_hash,
                (first_name or "").strip() or None,
                (last_name or "").strip() or None,
                phone_normalized,
                phone_normalized,
                (email or "").strip().lower() or None,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, username, first_name, last_name, phone, email, created_at FROM users WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        return dict(row) if row else None
    except sqlite3.IntegrityError:
        return None


def get_user_by_username(username: str) -> dict | None:
    """Fetch user by username (case-insensitive)."""
    conn = get_conn()
    row = conn.execute(
        "SELECT id, username, password_hash, first_name, last_name, phone, email, created_at FROM users WHERE LOWER(username) = ?",
        (username.strip().lower(),),
    ).fetchone()
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> dict | None:
    """Fetch user by id (without password_hash for safe use)."""
    conn = get_conn()
    row = conn.execute(
        "SELECT id, username, first_name, last_name, phone, email, created_at FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    return dict(row) if row else None


def get_user_by_phone(phone: str) -> dict | None:
    """Fetch user by phone (normalized). Phone is the stable unique identifier for messaging."""
    key = normalize_phone(phone)
    if not key:
        return None
    conn = get_conn()
    row = conn.execute(
        "SELECT id, username, first_name, last_name, phone, email, created_at FROM users WHERE normalized_phone = ?",
        (key,),
    ).fetchone()
    return dict(row) if row else None


def verify_password(user: dict, password: str) -> bool:
    """Check password against user's password_hash."""
    return check_password_hash(user["password_hash"], password)
