"""Agent worker: evaluates rules on events, calls LLM to create drafts, stores drafts, notifies UI.

Uses memory (follow-up success) and confidence for autonomy: high → auto-send, medium → ask approval, low → do nothing.
"""

from agent.events import TIMER_ELAPSED, register_handler
from agent.parser import generate_followup_draft
from agent.rules import create_draft, get_rule
from agent.memory import get_follow_up_success_summary, record_follow_up_sent, record_key_moment, mark_pending_follow_ups_no_reply
from agent.confidence import compute_confidence, should_auto_send, should_ask_approval, should_do_nothing
from agent.conversation_state import get_conversation_state
from messaging.models import get_messages, get_participant_ids


def _recipient_replied_since(conversation_id: int, rule_user_id: int, since_message_id: int | None) -> bool:
    """True if the other participant (recipient) has sent any message with id > since_message_id."""
    if since_message_id is None:
        since_message_id = 0
    participant_ids = get_participant_ids(conversation_id)
    recipient_id = next((x for x in participant_ids if x != rule_user_id), None)
    if not recipient_id:
        return False
    messages = get_messages(conversation_id, limit=100)
    for m in messages:
        if m["id"] > since_message_id and m["sender_id"] == recipient_id:
            return True
    return False


def _i_sent_after(conversation_id: int, rule_user_id: int, since_message_id: int | None) -> bool:
    """True if the rule owner sent any message with id > since_message_id (avoid double-text: one follow-up per rule)."""
    if since_message_id is None:
        since_message_id = 0
    messages = get_messages(conversation_id, limit=100)
    for m in messages:
        if m["id"] > since_message_id and m["sender_id"] == rule_user_id:
            return True
    return False


def _on_timer_elapsed(event_type: str, payload: dict) -> None:
    """Handle timer_elapsed: if rule is no_reply and recipient hasn't replied, create draft and push to UI."""
    if event_type != TIMER_ELAPSED:
        return
    rule_id = payload.get("rule_id")
    conversation_id = payload.get("conversation_id")
    user_id = payload.get("user_id")
    if not rule_id or not conversation_id or not user_id:
        return
    rule = get_rule(rule_id, user_id=None)
    if not rule or not rule.get("is_active") or rule["trigger"] != "no_reply":
        return
    if rule["user_id"] != user_id:
        return
    since_message_id = rule.get("trigger_since_message_id")
    if _recipient_replied_since(conversation_id, int(rule["user_id"]), since_message_id):
        return
    if _i_sent_after(conversation_id, int(rule["user_id"]), since_message_id):
        return
    action = rule.get("action") or "generate_followup"
    if action != "generate_followup":
        return

    rule_user_id = int(rule["user_id"])
    state = get_conversation_state(conversation_id, rule_user_id)
    memory_summary = get_follow_up_success_summary(conversation_id, rule_user_id)
    confidence_result = compute_confidence(
        conversation_id, rule_user_id, rule=rule, conversation_state=state, memory_summary=memory_summary
    )

    message_hint = rule.get("message_hint") or "follow up"
    tone = rule.get("tone")

    if should_do_nothing(confidence_result):
        record_key_moment(conversation_id, rule_user_id, "follow_up_skipped_low_confidence", confidence_result.reason)
        return

    content = generate_followup_draft(message_hint, tone, memory_summary=memory_summary or None)

    if should_auto_send(confidence_result):
        auto_send_callback = payload.get("auto_send_callback")
        if callable(auto_send_callback):
            mark_pending_follow_ups_no_reply(conversation_id, rule_user_id)
            auto_send_callback(conversation_id, rule_user_id, content)
            record_follow_up_sent(
                conversation_id=conversation_id,
                sender_id=rule_user_id,
                content_preview=content[:200] if content else None,
                tone_used=tone,
                draft_id=None,
            )
            record_key_moment(conversation_id, rule_user_id, "follow_up_auto_sent", "High confidence; sent without approval.")
        else:
            draft = create_draft(
                conversation_id=conversation_id,
                sender_id=rule_user_id,
                content=content,
                rule_id=rule_id,
            )
            push_draft_callback = payload.get("push_draft_to_ui")
            if push_draft_callback and callable(push_draft_callback):
                push_draft_callback(draft)
    elif should_ask_approval(confidence_result):
        draft = create_draft(
            conversation_id=conversation_id,
            sender_id=rule_user_id,
            content=content,
            rule_id=rule_id,
        )
        push_draft_callback = payload.get("push_draft_to_ui")
        if push_draft_callback and callable(push_draft_callback):
            push_draft_callback(draft)
    else:
        record_key_moment(conversation_id, rule_user_id, "follow_up_skipped", confidence_result.reason)


def start_agent_worker(
    push_draft_to_ui_callback=None,
    auto_send_callback=None,
):
    """Register the agent worker handler for timer_elapsed.
    push_draft_to_ui_callback(draft) when creating a draft for approval.
    auto_send_callback(conversation_id, sender_id, content) when auto-sending (high confidence).
    """
    def handler(event_type: str, payload: dict) -> None:
        payload = {**payload, "push_draft_to_ui": push_draft_to_ui_callback, "auto_send_callback": auto_send_callback}
        _on_timer_elapsed(event_type, payload)

    register_handler(TIMER_ELAPSED, handler)
