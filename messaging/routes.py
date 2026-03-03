"""API routes for conversations and messages (in-app chat)."""

from flask import Blueprint, request, jsonify, g, current_app

from agent.contacts import load_contacts
from agent.parser import expand_message_for_in_app
from auth.models import get_user_by_username, get_user_by_id, get_user_by_phone, normalize_phone
from messaging.models import (
    get_or_create_conversation,
    get_conversation,
    get_conversations_for_user,
    add_message,
    get_messages,
    get_participant_ids,
    get_max_message_id,
    get_unread_count,
    set_last_read,
)
from agent.rules import create_rule, get_pending_drafts_for_user, get_draft, get_rule, resolve_draft, resolve_pending_reply_suggestions
from agent.conversation_state import get_conversation_state
from agent.policy import intent_to_policy, compute_adaptive_delay_seconds
from agent.memory import (
    mark_follow_up_led_to_reply,
    record_follow_up_sent,
    get_recent_key_moments,
    get_follow_up_outcomes,
    get_follow_up_success_summary,
)

bp = Blueprint("messaging", __name__, url_prefix="/api")


def _message_to_json(msg: dict, sender_username: str | None = None) -> dict:
    return {
        "id": msg["id"],
        "conversation_id": msg["conversation_id"],
        "sender_id": msg["sender_id"],
        "sender_username": sender_username,
        "content": msg["content"],
        "created_at": msg["created_at"],
    }


def _phones_in_my_contacts() -> set[str]:
    """Set of normalized phone numbers from my contact list (contacts.json)."""
    contacts = load_contacts()
    out = set()
    for alias, phone in (contacts or {}).items():
        n = normalize_phone(phone)
        if n:
            out.add(n)
    return out


@bp.route("/users")
def list_users():
    """List users for starting a conversation. Excludes current user.
    Query params:
      in_my_contacts=1 - only users whose phone is in my contact list (contacts.json)
      phone=+1... - return single user by phone (404 if not found or not registered)
    """
    from auth.db import get_conn
    in_my_contacts = request.args.get("in_my_contacts", "").strip() == "1"
    search_phone = request.args.get("phone", "").strip()

    if search_phone:
        user = get_user_by_phone(search_phone)
        if not user or user["id"] == g.current_user["id"]:
            return jsonify({"error": "User not found or not registered with this phone"}), 404
        return jsonify([dict(user)])

    conn = get_conn()
    if in_my_contacts:
        phones = _phones_in_my_contacts()
        if not phones:
            return jsonify([])
        placeholders = ",".join("?" * len(phones))
        rows = conn.execute(
            f"SELECT id, username, first_name, last_name, phone FROM users WHERE id != ? AND normalized_phone IN ({placeholders}) ORDER BY first_name, username",
            (g.current_user["id"], *phones),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, username, first_name, last_name, phone FROM users WHERE id != ? ORDER BY first_name, username",
            (g.current_user["id"],),
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route("/conversations", methods=["GET"])
def list_conversations():
    """List current user's conversations with last message preview and unread count."""
    convos = get_conversations_for_user(g.current_user["id"])
    uid = g.current_user["id"]
    for c in convos:
        c["unread_count"] = get_unread_count(c["id"], uid)
    return jsonify(convos)


@bp.route("/conversations", methods=["POST"])
def create_conversation():
    """Start or get a 1:1 conversation. Body: { "user_id": 2 } | { "username": "alice" } | { "phone": "+15551234567" }."""
    data = request.get_json() or {}
    other_user = None
    if data.get("user_id"):
        other_user = get_user_by_id(int(data["user_id"]))
    elif data.get("username"):
        other_user = get_user_by_username((data["username"] or "").strip())
    elif data.get("phone"):
        other_user = get_user_by_phone((data["phone"] or "").strip())
    if not other_user:
        return jsonify({"error": "User not found or not registered with this phone"}), 404
    if other_user["id"] == g.current_user["id"]:
        return jsonify({"error": "Cannot start a conversation with yourself"}), 400
    conv = get_or_create_conversation(g.current_user["id"], other_user["id"])
    return jsonify(conv), 201


@bp.route("/conversations/<int:conversation_id>/read", methods=["POST"])
def mark_conversation_read(conversation_id: int):
    """Mark conversation as read (up to the latest message)."""
    conv = get_conversation(conversation_id, g.current_user["id"])
    if not conv:
        return jsonify({"error": "Conversation not found"}), 404
    max_id = get_max_message_id(conversation_id)
    if max_id is not None:
        set_last_read(conversation_id, g.current_user["id"], max_id)
    return jsonify({"success": True}), 200


@bp.route("/conversations/<int:conversation_id>/state", methods=["GET"])
def get_conversation_state_api(conversation_id: int):
    """Get computed conversation state (behavioral signals) for the current user's perspective."""
    conv = get_conversation(conversation_id, g.current_user["id"])
    if not conv:
        return jsonify({"error": "Conversation not found"}), 404
    state = get_conversation_state(conversation_id, g.current_user["id"])
    return jsonify(state)


@bp.route("/conversations/<int:conversation_id>/memory", methods=["GET"])
def get_conversation_memory_api(conversation_id: int):
    """Get memory layer for this conversation: key moments and follow-up success summary."""
    conv = get_conversation(conversation_id, g.current_user["id"])
    if not conv:
        return jsonify({"error": "Conversation not found"}), 404
    uid = g.current_user["id"]
    key_moments = get_recent_key_moments(conversation_id, uid, limit=20)
    follow_up_outcomes = get_follow_up_outcomes(conversation_id, uid, limit=10)
    success_summary = get_follow_up_success_summary(conversation_id, uid, last_n=5)
    return jsonify({
        "key_moments": key_moments,
        "follow_up_outcomes": follow_up_outcomes,
        "follow_up_success_summary": success_summary,
    })


@bp.route("/conversations/<int:conversation_id>/messages", methods=["GET"])
def list_messages(conversation_id: int):
    """Get messages for a conversation (paginated)."""
    conv = get_conversation(conversation_id, g.current_user["id"])
    if not conv:
        return jsonify({"error": "Conversation not found"}), 404
    before_id = request.args.get("before_id", type=int)
    messages = get_messages(conversation_id, limit=100, before_id=before_id)
    out = []
    for m in messages:
        sender = get_user_by_id(m["sender_id"])
        out.append(_message_to_json(m, sender["username"] if sender else None))
    return jsonify(out)


def _other_username_in_conversation(conversation_id: int, current_user_id: int) -> str | None:
    """Get the other participant's username in this 1:1 conversation."""
    from auth.db import get_conn
    conn = get_conn()
    row = conn.execute(
        """SELECT u.username FROM conversation_participants p
           JOIN users u ON u.id = p.user_id
           WHERE p.conversation_id = ? AND p.user_id != ?""",
        (conversation_id, current_user_id),
    ).fetchone()
    return row["username"] if row else None


@bp.route("/conversations/<int:conversation_id>/messages", methods=["POST"])
def send_message(conversation_id: int):
    """Send a message. Body: { "content": "..." }. All content is treated as natural-language intent.
    User defines intent → Agent decides when/how/whether to send (now vs scheduled).
    """
    conv = get_conversation(conversation_id, g.current_user["id"])
    if not conv:
        return jsonify({"error": "Conversation not found"}), 404
    data = request.get_json() or {}
    raw_content = (data.get("content") or "").strip()
    if not raw_content:
        return jsonify({"error": "Message content is required"}), 400

    other_username = _other_username_in_conversation(conversation_id, g.current_user["id"])
    conversation_context = {"other_username": other_username} if other_username else None

    parse_callback = current_app.config.get("parse_intent_callback")
    schedule_from_parsed_callback = current_app.config.get("schedule_in_app_from_parsed_callback")
    push_callback = current_app.config.get("push_message_to_ws_callback")

    parsed = None
    if parse_callback:
        try:
            parsed = parse_callback(raw_content, conversation_context)
        except Exception:
            current_app.logger.exception("parse intent")
    if not parsed or not (getattr(parsed, "message", None) or "").strip():
        parsed = None

    # Resolve content: use parsed message when present; for in-app, expand if parser failed or returned raw
    content_to_send = (parsed.message or "").strip() if parsed and (parsed.message or "").strip() else raw_content
    if conversation_context and (not content_to_send or content_to_send == raw_content):
        content_to_send = expand_message_for_in_app(raw_content)
    if not content_to_send:
        content_to_send = raw_content

    if parsed and schedule_from_parsed_callback:
        delay = getattr(parsed, "delay_seconds", None) or 0
        repeat_interval = getattr(parsed, "repeat_interval_seconds", None) or 0
        repeat_duration = getattr(parsed, "repeat_duration_seconds", None) or 0
        should_schedule = (delay is not None and delay > 0) or (repeat_interval > 0 and repeat_duration > 0)
        if should_schedule:
            from types import SimpleNamespace
            parsed_for_job = SimpleNamespace(
                message=content_to_send,
                contact_alias=getattr(parsed, "contact_alias", ""),
                delay_seconds=delay,
                scheduled_time=getattr(parsed, "scheduled_time"),
                raw_input=getattr(parsed, "raw_input", ""),
                repeat_interval_seconds=repeat_interval or None,
                repeat_duration_seconds=repeat_duration or None,
                repeat_stop_on_recipient_reply=getattr(parsed, "repeat_stop_on_recipient_reply", False),
            )
            scheduled = schedule_from_parsed_callback(parsed_for_job, conversation_id, g.current_user["id"])
            if scheduled:
                return jsonify({
                    "scheduled": True,
                    "send_at": scheduled.get("send_at"),
                    "message": content_to_send,
                    "raw_intent": raw_content,
                    "repeat_count": scheduled.get("repeat_count"),
                }), 202
    msg = add_message(conversation_id, g.current_user["id"], content_to_send)

    resolve_pending_reply_suggestions(conversation_id, g.current_user["id"])

    on_added = current_app.config.get("on_message_added_callback")
    if on_added:
        on_added(conversation_id, g.current_user["id"], msg["id"], msg.get("content"))

    participants = get_participant_ids(conversation_id)
    other_id = next((p for p in participants if p != g.current_user["id"]), None)
    if other_id is not None:
        mark_follow_up_led_to_reply(conversation_id, other_id)

    if push_callback:
        push_callback(msg, conversation_id)
    check_callback = current_app.config.get("check_repeat_stop_on_message_callback")
    if check_callback:
        check_callback(conversation_id, g.current_user["id"], content_to_send)

    # If parsed intent is no_reply, create rule and schedule timer_elapsed (fixed or adaptive)
    if parsed and getattr(parsed, "trigger", None) == "no_reply":
        schedule_timer = current_app.config.get("schedule_timer_elapsed_callback")
        if schedule_timer:
            fixed_duration = getattr(parsed, "trigger_duration_seconds", None)
            if fixed_duration and fixed_duration > 0:
                delay_seconds = fixed_duration
            else:
                state = get_conversation_state(conversation_id, g.current_user["id"])
                policy = intent_to_policy(getattr(parsed, "raw_input", "") or "", state)
                delay_seconds = compute_adaptive_delay_seconds(
                    policy, state, default_fallback_seconds=14400
                )
            rule = create_rule(
                conversation_id,
                g.current_user["id"],
                trigger="no_reply",
                trigger_duration_seconds=delay_seconds,
                trigger_since_message_id=msg["id"],
                action=getattr(parsed, "action", "generate_followup") or "generate_followup",
                tone=getattr(parsed, "tone", None),
                message_hint=(getattr(parsed, "message", None) or "follow up").strip() or "follow up",
                raw_intent=getattr(parsed, "raw_input", None),
            )
            schedule_timer(rule["id"], conversation_id, g.current_user["id"], delay_seconds)

    sender = get_user_by_id(msg["sender_id"])
    return jsonify(_message_to_json(msg, sender["username"] if sender else None)), 201


# ----- Drafts (agent-generated messages awaiting approval) -----


@bp.route("/drafts", methods=["GET"])
def list_drafts():
    """List pending drafts for the current user (sender)."""
    drafts = get_pending_drafts_for_user(g.current_user["id"])
    return jsonify(drafts)


@bp.route("/drafts/<int:draft_id>/approve", methods=["POST"])
def approve_draft(draft_id: int):
    """Approve a draft: send its content as a message and resolve the draft."""
    draft = get_draft(draft_id, g.current_user["id"])
    if not draft:
        return jsonify({"error": "Draft not found or not yours"}), 404
    if draft.get("status") != "pending":
        return jsonify({"error": "Draft already resolved"}), 400
    conversation_id = draft["conversation_id"]
    conv = get_conversation(conversation_id, g.current_user["id"])
    if not conv:
        return jsonify({"error": "Conversation not found"}), 404
    resolved = resolve_draft(draft_id, g.current_user["id"], "approved")
    if not resolved:
        return jsonify({"error": "Draft could not be resolved"}), 400
    msg = add_message(conversation_id, g.current_user["id"], draft["content"])
    push_callback = current_app.config.get("push_message_to_ws_callback")
    if push_callback:
        push_callback(msg, conversation_id)
    on_added = current_app.config.get("on_message_added_callback")
    if on_added:
        on_added(conversation_id, g.current_user["id"], msg["id"], msg.get("content"))
    if draft.get("rule_id"):
        rule = get_rule(draft["rule_id"], user_id=None) if draft.get("rule_id") else None
        tone_used = rule.get("tone") if rule else None
        record_follow_up_sent(
            conversation_id=conversation_id,
            sender_id=g.current_user["id"],
            content_preview=(draft.get("content") or "")[:200],
            tone_used=tone_used,
            draft_id=draft_id,
        )
    return jsonify({"success": True, "message": _message_to_json(msg, g.current_user.get("username"))}), 200


@bp.route("/drafts/<int:draft_id>/reject", methods=["POST"])
def reject_draft(draft_id: int):
    """Reject a draft: mark as rejected, do not send."""
    draft = get_draft(draft_id, g.current_user["id"])
    if not draft:
        return jsonify({"error": "Draft not found or not yours"}), 404
    if draft.get("status") != "pending":
        return jsonify({"error": "Draft already resolved"}), 400
    resolved = resolve_draft(draft_id, g.current_user["id"], "rejected")
    if not resolved:
        return jsonify({"error": "Draft could not be resolved"}), 400
    return jsonify({"success": True}), 200
