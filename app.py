#!/usr/bin/env python3
"""Web UI for the Scheduled Messenger Agent."""

import json
import queue
import threading
from datetime import datetime, timedelta

from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, Response

from agent.parser import parse_request
from agent.scheduler import Scheduler
from agent.contacts import load_contacts, get_phone, add_contact
from agent.sent_messages import record_sent_message, load_sent_messages

load_dotenv()

app = Flask(__name__)
scheduler = None
sent_event_queues: list[queue.Queue] = []
queues_lock = threading.Lock()


def broadcast_sent(message: str, contact_alias: str, phone: str):
    """Push sent notification to all connected SSE clients and record to history."""
    sent_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    record_sent_message(message, contact_alias, phone, sent_at)
    data = {
        "type": "sent",
        "message": message,
        "contact_alias": contact_alias,
        "phone": phone,
        "sent_at": sent_at,
    }
    with queues_lock:
        for q in sent_event_queues:
            try:
                q.put_nowait(data)
            except queue.Full:
                pass


def get_scheduler() -> Scheduler:
    """Get or create the shared scheduler instance."""
    global scheduler
    if scheduler is None:
        scheduler = Scheduler()
    return scheduler


@app.route("/")
def index():
    """Serve the main UI."""
    return render_template(
        "index.html",
        contacts=load_contacts(),
        sent_messages=load_sent_messages(),
    )


@app.route("/schedule", methods=["POST"])
def schedule():
    """Parse and schedule a message from natural language request."""
    data = request.get_json() or {}
    request_text = (data.get("request") or "").strip()

    if not request_text:
        return jsonify({"error": "Please enter a message request"}), 400

    try:
        scheduled = parse_request(request_text)
    except Exception as e:
        return jsonify({"error": f"Could not parse request: {e}"}), 400

    phone = get_phone(scheduled.contact_alias)
    if not phone:
        return jsonify({
            "error": f"Unknown contact '{scheduled.contact_alias}'. Add them first with: python main.py add-contact {scheduled.contact_alias} +1XXXXXXXXXX"
        }), 400

    if scheduled.delay_seconds is None:
        return jsonify({"error": "Could not determine when to send. Try phrases like 'in 1 hour' or 'in 30 minutes'"}), 400

    try:
        sched = get_scheduler()
        sched.schedule_message(
            scheduled.message,
            scheduled.contact_alias,
            scheduled.delay_seconds,
            on_sent_callback=broadcast_sent,
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    send_at = datetime.now() + timedelta(seconds=scheduled.delay_seconds)
    return jsonify({
        "success": True,
        "message": scheduled.message,
        "contact_alias": scheduled.contact_alias,
        "phone": phone,
        "send_at": send_at.strftime("%H:%M:%S"),
        "delay_seconds": scheduled.delay_seconds,
    })


@app.route("/contacts", methods=["POST"])
def add_contact_api():
    """Add a new contact via the UI."""
    data = request.get_json() or {}
    alias = (data.get("alias") or "").strip()
    phone = (data.get("phone") or "").strip()

    if not alias:
        return jsonify({"error": "Alias is required (e.g. wife, mom)"}), 400
    if not phone:
        return jsonify({"error": "Phone number is required (e.g. +15551234567)"}), 400

    add_contact(alias, phone)
    return jsonify({"success": True, "alias": alias.lower(), "phone": phone})


@app.route("/events")
def events():
    """Server-Sent Events stream for real-time sent notifications."""

    def generate():
        q = queue.Queue()
        with queues_lock:
            sent_event_queues.append(q)
        try:
            while True:
                event = q.get()
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            with queues_lock:
                if q in sent_event_queues:
                    sent_event_queues.remove(q)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


if __name__ == "__main__":
    # Port 5000 often used by macOS AirPlay - use 5001
    app.run(debug=True, host="0.0.0.0", port=5001)
