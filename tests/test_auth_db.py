"""Unit tests for auth.db."""

import sqlite3

import pytest

from auth.db import get_conn, init_db, DB_PATH


def test_db_path_uses_test_env():
    """AUTH_DB_PATH from conftest should point to temp test file."""
    assert "test_auth.db" in DB_PATH or "scheduled_messenger_test" in DB_PATH


def test_init_db_creates_users_table():
    """init_db creates users table with expected columns."""
    init_db()
    conn = get_conn()
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
    ).fetchone()
    assert row is not None
    # Check columns exist
    cursor = conn.execute("PRAGMA table_info(users)")
    columns = {r[1] for r in cursor.fetchall()}
    assert "id" in columns
    assert "username" in columns
    assert "password_hash" in columns
    assert "created_at" in columns
    assert "first_name" in columns
    assert "last_name" in columns
    assert "phone" in columns
    assert "email" in columns


def test_get_conn_returns_connection_with_row_factory():
    """get_conn returns a connection that returns dict-like rows."""
    conn = get_conn()
    assert conn is not None
    conn.execute("SELECT 1 AS one")
    row = conn.execute("SELECT 1 AS one").fetchone()
    # row_factory is sqlite3.Row, so row can be indexed by name
    assert row["one"] == 1
