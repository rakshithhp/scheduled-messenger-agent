#!/usr/bin/env python3
"""
Scheduled Messenger Agent

Example: python main.py "Send a good night text to my wife after an hour"
"""

import argparse
import sys
from datetime import datetime

from dotenv import load_dotenv

from agent.parser import parse_request
from agent.scheduler import Scheduler
from agent.contacts import load_contacts, add_contact, get_phone
from agent.sent_messages import record_sent_message, load_sent_messages

load_dotenv()


def notify_sent(message: str, contact_alias: str, phone: str):
    """Called when message is sent - notify the user and record to history."""
    record_sent_message(message, contact_alias, phone)
    print(f"\n✓ Message sent to {contact_alias} ({phone}):")
    print(f"  \"{message}\"")
    print(f"  Sent at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Schedule messages to contacts. Example: 'Send good night to wife in 1 hour'"
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # schedule command (default) - also works without subcommand
    schedule_parser = subparsers.add_parser("schedule", help="Schedule a message")
    schedule_parser.add_argument("request", nargs="+", help='e.g. "Send good night to wife in an hour"')
    schedule_parser.add_argument("--dry-run", action="store_true", help="Parse only, don't schedule")

    # add-contact command
    contact_parser = subparsers.add_parser("add-contact", help="Add a contact alias → phone")
    contact_parser.add_argument("alias", help="e.g. wife, mom")
    contact_parser.add_argument("phone", help="e.g. +15551234567")

    # list contacts
    subparsers.add_parser("contacts", help="List saved contacts")

    # list sent messages
    subparsers.add_parser("sent-messages", help="List sent message history")

    # If first arg isn't a known command, treat all args as the message request
    argv = sys.argv[1:]
    if argv and argv[0] not in ("schedule", "add-contact", "contacts", "sent-messages"):
        argv = ["schedule"] + argv

    args = parser.parse_args(argv)

    if args.command == "add-contact":
        add_contact(args.alias, args.phone)
        print(f"Added: {args.alias} → {args.phone}")
        return

    if args.command == "contacts":
        contacts = load_contacts()
        if not contacts:
            print("No contacts yet. Add one with: python main.py add-contact wife +15551234567")
        else:
            for alias, phone in contacts.items():
                print(f"  {alias}: {phone}")
        return

    if args.command == "sent-messages":
        messages = load_sent_messages()
        if not messages:
            print("No sent messages yet.")
        else:
            print("Sent messages (newest first):\n")
            for m in messages:
                print(f"  {m['sent_at']} │ {m['contact_alias']} ({m['phone']})")
                print(f"    \"{m['message']}\"")
                print()
        return

    # Default: schedule a message
    request = " ".join(args.request) if hasattr(args, "request") and args.request else None
    if not request:
        parser.print_help()
        print("\nExample: python main.py 'Send a good night text to my wife after an hour'")
        sys.exit(1)

    try:
        scheduled = parse_request(request)
        print(f"Parsed: send \"{scheduled.message}\" to {scheduled.contact_alias} in {scheduled.delay_seconds}s")

        phone = get_phone(scheduled.contact_alias)
        if not phone:
            print(f"\n✗ Unknown contact '{scheduled.contact_alias}'. Add them first:")
            print(f"  python main.py add-contact {scheduled.contact_alias} +1XXXXXXXXXX")
            sys.exit(1)

        if args.dry_run if hasattr(args, "dry_run") else False:
            print("(Dry run - not scheduling)")
            return

        scheduler = Scheduler()
        scheduler.schedule_message(
            scheduled.message,
            scheduled.contact_alias,
            scheduled.delay_seconds,
            on_sent_callback=notify_sent,
        )

        from datetime import timedelta
        send_at = datetime.now() + timedelta(seconds=scheduled.delay_seconds)
        print(f"Scheduled for {send_at.strftime('%H:%M:%S')}. I'll notify you when it's sent.")
        print("(Keep this process running until the message is sent)\n")

        # Keep process alive
        import time
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            print("\nShutting down...")
            scheduler.shutdown()

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
