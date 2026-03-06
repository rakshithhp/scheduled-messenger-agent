"""Reply suggestion: when someone messages you, the agent drafts a possible reply and shows it for approval."""

import os
import re
import unicodedata
from typing import Callable

from openai import OpenAI

from agent.rules import create_draft, get_pending_drafts_for_conversation, resolve_pending_reply_suggestions
from messaging.models import get_messages, get_participant_ids

# Phrases that typically end a conversation; avoid suggesting another reply after these.
CLOSING_PATTERN = re.compile(
    r"\b(bye|goodbye|see you|talk to you|thanks|thank you|thank u|thx|take care|"
    r"good night|gn|catch you later|have a good one|later|ttyl|cya|ok bye|okay bye)\b",
    re.I,
)


def _looks_like_closing(text: str) -> bool:
    """True if the message looks like a sign-off or closing (so we can avoid farewell loops)."""
    if not (text or text.strip()):
        return False
    t = text.strip()
    if len(t) > 120:
        return False
    return bool(CLOSING_PATTERN.search(t))


def _is_emoji_or_smiley_only(text: str) -> bool:
    """True if the message is only/mostly emoji/smileys (avoid reply-suggestion loops on emoji)."""
    if not (text or text.strip()):
        return True
    t = text.strip()
    if len(t) > 20:
        return False
    # Remove common emoji/symbols and see if anything substantial remains
    rest = []
    for c in t:
        cat = unicodedata.category(c)
        if cat == "So" or cat == "Sk" or c in "👍👋😀😊🙂😉😎🤗😁😂🤣❤️💙🙏✨":
            continue
        if cat.startswith("L") or cat == "Nd" or c in "?!.,":
            rest.append(c)
    return len(rest) <= 1


def _last_message_from_recipient_was_closing(recent_messages: list[dict], recipient_id: int) -> bool:
    """True if the most recent message from the recipient (the user we're suggesting for) was a closing."""
    for m in reversed(recent_messages or []):
        if m.get("sender_id") == recipient_id:
            return _looks_like_closing((m.get("content") or ""))
    return False


REPLY_SUGGESTION_PROMPT = """You suggest a short, natural reply to a message in a 1:1 chat.

Recent conversation (oldest to newest):
{context}

The other person just said:
"{incoming_message}"

Rules:
- Suggest ONE short reply. Match the tone and keep it concise. Output only the reply text, no quotes or explanation.
- If their message is a closing or sign-off (e.g. "see you", "bye", "talk to you", "thanks", "thank you", "take care", "good night", "catch you later", "have a good one"), do NOT suggest another full farewell or thank-you that would invite yet another reply. Either output a single brief sign-off like "Bye!" or "See you!" or "👍" or output nothing. Prefer ending the thread, not continuing it.
- If the last few exchanges are already back-and-forth goodbyes or thanks, output nothing (so the conversation can end)."""


def generate_reply_suggestion(
    recent_messages: list[dict],
    incoming_message_content: str,
    recipient_id: int,
) -> str:
    """Generate a suggested reply using the LLM. recipient_id = user we're suggesting for (labels as 'You')."""
    if not (incoming_message_content or incoming_message_content.strip()):
        return ""
    # Avoid loop on emoji/smiley-only messages (e.g. 👍😀) — don't suggest another emoji reply.
    if _is_emoji_or_smiley_only(incoming_message_content):
        return ""
    # Avoid farewell loop: if they said a closing and we already said a closing, don't suggest again.
    if _looks_like_closing(incoming_message_content) and _last_message_from_recipient_was_closing(
        recent_messages or [], recipient_id
    ):
        return ""
    context_parts = []
    for m in (recent_messages or [])[-15:]:
        who = "You" if m.get("sender_id") == recipient_id else "They"
        context_parts.append(f"{who}: {m.get('content', '')}")
    context = "\n".join(context_parts) if context_parts else "(no prior messages)"
    prompt = REPLY_SUGGESTION_PROMPT.format(
        context=context[:1500],
        incoming_message=incoming_message_content.strip()[:500],
    )
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
        )
        content = (response.choices[0].message.content or "").strip()
        if content and content.startswith('"') and content.endswith('"'):
            content = content[1:-1]
        return content if content else ""
    except Exception:
        return ""


def on_message_received_for_reply_suggestion(
    event_type: str,
    payload: dict,
    push_draft_to_ui: Callable[[dict], None] | None = None,
) -> None:
    """
    When a message is received (someone else sent it), suggest a reply to the recipient(s).
    Creates a draft (rule_id=None) and pushes to UI for approval. One pending reply-suggestion per conversation per user.
    """
    if event_type != "message_received":
        return
    conversation_id = payload.get("conversation_id")
    sender_id = payload.get("sender_id")
    content = payload.get("content") or ""
    if not conversation_id or not sender_id:
        return
    participant_ids = get_participant_ids(conversation_id)
    recipient_ids = [p for p in participant_ids if p != sender_id]
    if not recipient_ids:
        return
    for recipient_id in recipient_ids:
        resolve_pending_reply_suggestions(conversation_id, recipient_id)
        recent = get_messages(conversation_id, limit=20)
        suggested = generate_reply_suggestion(recent, content, recipient_id)
        if not suggested:
            continue
        draft = create_draft(
            conversation_id=conversation_id,
            sender_id=recipient_id,
            content=suggested,
            rule_id=None,
        )
        if push_draft_to_ui and callable(push_draft_to_ui):
            push_draft_to_ui(draft)
