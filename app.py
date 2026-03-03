#!/usr/bin/env python3
"""Web UI for the Scheduled Messenger Agent."""

import json
import os
import queue
import threading
from datetime import datetime, timedelta

from apscheduler.triggers.date import DateTrigger
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, Response, g, redirect, url_for
from flask_sock import Sock

from agent.parser import parse_request, should_stop_repeat
from agent.scheduler import Scheduler
from agent.contacts import load_contacts, get_phone, add_contact
from agent.sent_messages import record_sent_message, load_sent_messages
from agent.events import emit, MESSAGE_SENT, MESSAGE_RECEIVED, TIMER_ELAPSED, register_handler
from agent.worker import start_agent_worker
from agent.reply_suggestion import on_message_received_for_reply_suggestion
from auth import init_db
from auth.jwt_utils import decode_token
from auth.models import get_user_by_id
from auth.routes import bp as auth_bp
from messaging.models import add_message as messaging_add_message, get_participant_ids, get_messages as messaging_get_messages
from messaging.routes import bp as messaging_bp

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
app.config["JWT_SECRET"] = os.environ.get("JWT_SECRET", app.secret_key)
sock = Sock(app)

init_db()
app.register_blueprint(auth_bp)
app.register_blueprint(messaging_bp)

scheduler = None
sent_event_queues: list[queue.Queue] = []
queues_lock = threading.Lock()

# WebSocket: user_id -> set of active ws connections
ws_connections: dict[int, set] = {}
ws_lock = threading.Lock()

# Active repeat series: (conversation_id, repeat_sender_id) -> {"job_ids": [...], "message": str}
repeat_series: dict[tuple[int, int], dict] = {}
repeat_series_lock = threading.Lock()


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


def push_message_to_ws(msg: dict, conversation_id: int):
    """Push a new message to all participants' WebSocket connections."""
    from auth.models import get_user_by_id
    payload = {
        "type": "new_message",
        "conversation_id": conversation_id,
        "message": {
            "id": msg["id"],
            "sender_id": msg["sender_id"],
            "content": msg["content"],
            "created_at": msg["created_at"],
        },
    }
    sender = get_user_by_id(msg["sender_id"])
    if sender:
        payload["message"]["sender_username"] = sender["username"]
    participant_ids = get_participant_ids(conversation_id)
    body = json.dumps(payload)
    with ws_lock:
        for uid in participant_ids:
            for ws in ws_connections.get(uid, set()).copy():
                try:
                    ws.send(body)
                except Exception:
                    pass


def on_message_added(
    conversation_id: int,
    sender_id: int,
    message_id: int,
    content: str | None = None,
) -> None:
    """Emit message_sent and message_received when a message is added (route or scheduler)."""
    payload = {
        "conversation_id": conversation_id,
        "sender_id": sender_id,
        "message_id": message_id,
        "content": content or "",
    }
    emit(MESSAGE_SENT, payload)
    emit(MESSAGE_RECEIVED, payload)


def schedule_timer_elapsed(rule_id: int, conversation_id: int, user_id: int, delay_seconds: int) -> None:
    """Schedule a one-shot job to emit TIMER_ELAPSED after delay_seconds (for no_reply rules)."""
    run_at = datetime.now() + timedelta(seconds=delay_seconds)
    job_id = f"timer_elapsed_rule_{rule_id}_{run_at.timestamp():.0f}"

    def job():
        emit(TIMER_ELAPSED, {"rule_id": rule_id, "conversation_id": conversation_id, "user_id": user_id})

    get_scheduler().scheduler.add_job(
        job,
        trigger=DateTrigger(run_date=run_at),
        id=job_id,
    )


def push_draft_to_ui(draft: dict) -> None:
    """Push a new draft to the rule owner's WebSocket connections (for approval/reject)."""
    user_id = draft.get("sender_id")
    if user_id is None:
        return
    payload = {"type": "new_draft", "draft": draft}
    body = json.dumps(payload)
    with ws_lock:
        for ws in ws_connections.get(user_id, set()).copy():
            try:
                ws.send(body)
            except Exception:
                pass


def auto_send_follow_up(conversation_id: int, sender_id: int, content: str) -> None:
    """Send a follow-up message immediately (high confidence). Used by the agent worker."""
    m = messaging_add_message(conversation_id, sender_id, content)
    push_message_to_ws(m, conversation_id)
    on_message_added(conversation_id, sender_id, m["id"], m.get("content"))


def parse_intent(raw_content: str, conversation_context: dict | None):
    """Parse user intent (natural language) into message + when. Agent decides when/how to send."""
    return parse_request(raw_content, conversation_context=conversation_context)


def schedule_in_app_from_parsed(parsed, conversation_id: int, sender_id: int):
    """Schedule an already-parsed intent (agent decided delay, optionally repeating). No second parse."""
    delay = getattr(parsed, "delay_seconds", None) or 0
    interval = getattr(parsed, "repeat_interval_seconds", None) or 0
    duration = getattr(parsed, "repeat_duration_seconds", None) or 0
    content = (getattr(parsed, "message", None) or "").strip()

    if interval > 0 and duration > 0:
        # Repeating: schedule one job per send from 0 to duration at interval steps; track for agent-driven stop
        n = max(1, duration // interval)
        sched = get_scheduler().scheduler
        base = datetime.now() + timedelta(seconds=delay)
        job_ids: list[str] = []

        def make_job(msg_content):
            def job():
                m = messaging_add_message(conversation_id, sender_id, msg_content)
                push_message_to_ws(m, conversation_id)
                on_message_added(conversation_id, sender_id, m["id"], m.get("content"))
            return job

        for i in range(n):
            run_at = base + timedelta(seconds=i * interval)
            job_id = f"inapp_{conversation_id}_{run_at.timestamp():.0f}_{i}"
            job_ids.append(job_id)
            sched.add_job(
                make_job(content),
                trigger=DateTrigger(run_date=run_at),
                id=job_id,
            )
        # Only register for agent-driven stop when user said "until they accept/reply" etc.; never for "every year" etc.
        stop_on_reply = getattr(parsed, "repeat_stop_on_recipient_reply", None) is True
        if stop_on_reply:
            raw_intent = (getattr(parsed, "raw_input", None) or "").strip()
            with repeat_series_lock:
                repeat_series[(conversation_id, sender_id)] = {
                    "job_ids": job_ids,
                    "message": content,
                    "raw_intent": raw_intent,
                }
        return {"scheduled": True, "send_at": base.isoformat(), "message": content, "repeat_count": n}
    if delay <= 0:
        return None
    run_at = datetime.now() + timedelta(seconds=delay)

    def job():
        m = messaging_add_message(conversation_id, sender_id, content)
        push_message_to_ws(m, conversation_id)
        on_message_added(conversation_id, sender_id, m["id"], m.get("content"))

    get_scheduler().scheduler.add_job(
        job,
        trigger=DateTrigger(run_date=run_at),
        id=f"inapp_{conversation_id}_{run_at.timestamp():.0f}",
    )
    return {"scheduled": True, "send_at": run_at.isoformat(), "message": content}


def cancel_repeat_series(conversation_id: int, repeat_sender_id: int) -> None:
    """Remove all scheduled jobs for this repeat series and clear the tracking entry."""
    with repeat_series_lock:
        entry = repeat_series.pop((conversation_id, repeat_sender_id), None)
    if not entry:
        return
    sched = get_scheduler().scheduler
    for job_id in entry.get("job_ids", []):
        try:
            sched.remove_job(job_id)
        except Exception:
            pass


def check_repeat_stop_on_message(conversation_id: int, message_sender_id: int, message_content: str) -> None:
    """When the recipient sends a message, ask the agent whether to stop the repeat; cancel remaining jobs if yes."""
    participant_ids = get_participant_ids(conversation_id)
    other_id = next((x for x in participant_ids if x != message_sender_id), None)
    if other_id is None:
        return
    with repeat_series_lock:
        entry = repeat_series.get((conversation_id, other_id))
    if not entry:
        return
    repeated_message = entry.get("message", "")
    raw_intent = entry.get("raw_intent", "")
    recent = messaging_get_messages(conversation_id, limit=15)
    if should_stop_repeat(repeated_message, message_content, recent, raw_intent=raw_intent):
        cancel_repeat_series(conversation_id, other_id)


app.config["push_message_to_ws_callback"] = push_message_to_ws
app.config["parse_intent_callback"] = parse_intent
app.config["schedule_in_app_from_parsed_callback"] = schedule_in_app_from_parsed
app.config["check_repeat_stop_on_message_callback"] = check_repeat_stop_on_message
app.config["on_message_added_callback"] = on_message_added
app.config["schedule_timer_elapsed_callback"] = schedule_timer_elapsed
app.config["push_draft_to_ui_callback"] = push_draft_to_ui

# Start agent worker: timer_elapsed creates drafts (or auto-sends when confidence high)
start_agent_worker(
    push_draft_to_ui_callback=push_draft_to_ui,
    auto_send_callback=auto_send_follow_up,
)


# Reply suggestion: when someone messages you, draft a possible reply and show for approval
def _reply_suggestion_handler(event_type: str, payload: dict) -> None:
    on_message_received_for_reply_suggestion(event_type, payload, push_draft_to_ui=push_draft_to_ui)


register_handler(MESSAGE_RECEIVED, _reply_suggestion_handler)


# Paths that do not require authentication (WS auth is done in handler)
PUBLIC_PATHS = {"/login", "/register", "/auth/login", "/auth/register", "/auth/logout", "/ws"}


def _get_token():
    """Extract token from cookie (for GET /) or Authorization header (for API/fetch)."""
    auth = request.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        return auth[7:].strip()
    if request.cookies.get("token"):
        return request.cookies.get("token")
    return request.args.get("token") or (request.form.get("token") if request.form else None)


@app.before_request
def require_auth():
    """Set g.current_user from JWT; redirect or 401 for protected routes if missing."""
    path = request.path
    if path in PUBLIC_PATHS:
        return None

    token = _get_token()
    g.current_user = None
    if token:
        payload = decode_token(token, secret=app.config.get("JWT_SECRET"))
        if payload and "sub" in payload:
            try:
                user_id = int(payload["sub"])
            except (TypeError, ValueError):
                user_id = None
            if user_id is not None:
                user = get_user_by_id(user_id)
                if user:
                    g.current_user = user

    if g.current_user is None:
        if path == "/" and request.method == "GET":
            return redirect(url_for("login_page"))
        return jsonify({"error": "Authentication required"}), 401
    return None


@app.route("/")
def index():
    """Serve the main UI (auth required)."""
    return render_template(
        "index.html",
        contacts=load_contacts(),
        sent_messages=load_sent_messages(),
        current_user=g.current_user,
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

    try:
        add_contact(alias, phone)
    except OSError as e:
        return jsonify({
            "error": "Could not save contact (server storage may be read-only). Set CONTACTS_FILE to a writable path (e.g. /var/app/data/contacts.json)."
        }), 503
    return jsonify({"success": True, "alias": alias.lower(), "phone": phone})


@app.route("/api/sent-messages")
def api_sent_messages():
    """Return sent messages as JSON for polling when SSE is unavailable."""
    return jsonify(load_sent_messages())


@app.route("/login")
def login_page():
    """Serve login page (no auth required)."""
    return render_template("login.html")


@app.route("/register")
def register_page():
    """Serve register page (no auth required)."""
    return render_template("register.html")


@sock.route("/ws")
def websocket(ws):
    """WebSocket: connect with ?token=JWT. Server pushes new_message events to clients."""
    token = request.args.get("token") or (ws.receive() if hasattr(ws, "receive") else None)
    if isinstance(token, bytes):
        token = token.decode("utf-8", errors="ignore")
    user = None
    if token:
        payload = decode_token(token, secret=app.config.get("JWT_SECRET"))
        if payload and "sub" in payload:
            try:
                uid = int(payload["sub"])
                user = get_user_by_id(uid)
            except (TypeError, ValueError):
                pass
    if not user:
        try:
            ws.send(json.dumps({"type": "error", "error": "Authentication required"}))
        except Exception:
            pass
        return
    user_id = user["id"]
    with ws_lock:
        if user_id not in ws_connections:
            ws_connections[user_id] = set()
        ws_connections[user_id].add(ws)
    try:
        while True:
            data = ws.receive()
            if data is None:
                break
            if isinstance(data, bytes):
                data = data.decode("utf-8", errors="ignore")
            if data and data.strip() == "ping":
                try:
                    ws.send(json.dumps({"type": "pong"}))
                except Exception:
                    break
    except Exception:
        pass
    finally:
        with ws_lock:
            if user_id in ws_connections:
                ws_connections[user_id].discard(ws)
                if not ws_connections[user_id]:
                    del ws_connections[user_id]


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
    # Use a high port to avoid conflicts (5000=AirPlay, 5001=common dev). Override with PORT=...
    port = int(os.environ.get("PORT", 5034))
    app.run(debug=True, host="0.0.0.0", port=port)
