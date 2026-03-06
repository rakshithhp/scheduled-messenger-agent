"""Pytest configuration and fixtures for auth tests.

Set AUTH_DB_PATH and JWT_SECRET before any auth code is imported so tests
use a temporary DB and a fixed secret.
"""

import os
import tempfile

import pytest

# Must set before any import of auth.* (so DB_PATH is correct when auth.db loads)
_test_db_dir = tempfile.mkdtemp(prefix="scheduled_messenger_test_")
os.environ["AUTH_DB_PATH"] = os.path.join(_test_db_dir, "test_auth.db")
# Use 32+ char secret to avoid PyJWT key length warning
os.environ["JWT_SECRET"] = "test-jwt-secret-for-unit-tests-only-32chars"


@pytest.fixture(scope="session", autouse=True)
def _init_auth_db():
    """Create users table once per test session."""
    from auth import init_db
    init_db()


@pytest.fixture(autouse=True)
def _clear_users_and_messaging():
    """Clear messaging tables, agent tables, and users before each test for isolation."""
    from auth.db import get_conn
    conn = get_conn()
    for table in (
        "device_tokens",
        "follow_up_outcomes",
        "key_moments",
        "conversation_embeddings",
        "conversation_read_state",
        "drafts",
        "rules",
        "messages",
        "conversation_participants",
        "conversations",
        "users",
    ):
        try:
            conn.execute(f"DELETE FROM {table}")
        except Exception:
            pass
    conn.commit()
