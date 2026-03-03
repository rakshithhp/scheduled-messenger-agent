"""Contact storage - maps aliases (wife, mom) to phone numbers."""

import json
from pathlib import Path

CONTACTS_FILE = Path(__file__).parent.parent / "contacts.json"


def load_contacts() -> dict[str, str]:
    """Load contact alias → phone number mapping."""
    if CONTACTS_FILE.exists():
        with open(CONTACTS_FILE) as f:
            return json.load(f)
    return {}


def save_contacts(contacts: dict[str, str]) -> None:
    """Save contacts to file."""
    with open(CONTACTS_FILE, "w") as f:
        json.dump(contacts, f, indent=2)


def get_phone(alias: str) -> str | None:
    """Get phone number for a contact alias."""
    return load_contacts().get(alias.lower())


def add_contact(alias: str, phone: str) -> None:
    """Add or update a contact."""
    contacts = load_contacts()
    contacts[alias.lower()] = phone
    save_contacts(contacts)
