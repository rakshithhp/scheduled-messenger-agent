"""Persistent log of sent messages."""

import json
from datetime import datetime
from pathlib import Path

SENT_MESSAGES_FILE = Path(__file__).parent.parent / "sent_messages.json"


def load_sent_messages() -> list[dict]:
    """Load the list of sent messages (newest first)."""
    if SENT_MESSAGES_FILE.exists():
        try:
            with open(SENT_MESSAGES_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
    return []


def record_sent_message(message: str, contact_alias: str, phone: str, sent_at: str | None = None) -> None:
    """Append a sent message to the log."""
    entry = {
        "message": message,
        "contact_alias": contact_alias,
        "phone": phone,
        "sent_at": sent_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    messages = load_sent_messages()
    messages.insert(0, entry)  # newest first
    with open(SENT_MESSAGES_FILE, "w") as f:
        json.dump(messages, f, indent=2)
