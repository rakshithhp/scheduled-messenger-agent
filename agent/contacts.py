"""Contact storage - maps aliases (wife, mom) to phone numbers."""

import json
import os
from pathlib import Path

_DEFAULT_PATH = Path(__file__).parent.parent / "contacts.json"
CONTACTS_FILE = Path(os.environ.get("CONTACTS_FILE", str(_DEFAULT_PATH)))


def load_contacts() -> dict[str, str]:
    """Load contact alias → phone number mapping."""
    if CONTACTS_FILE.exists():
        try:
            with open(CONTACTS_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_contacts(contacts: dict[str, str]) -> None:
    """Save contacts to file. Raises OSError if not writable (e.g. read-only filesystem on AWS)."""
    p = CONTACTS_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        json.dump(contacts, f, indent=2)


def get_phone(alias: str) -> str | None:
    """Get phone number for a contact alias."""
    return load_contacts().get(alias.lower())


def add_contact(alias: str, phone: str) -> None:
    """Add or update a contact."""
    contacts = load_contacts()
    contacts[alias.lower()] = phone
    save_contacts(contacts)
