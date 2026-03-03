"""Parse natural language into intent: what to send, when, and to whom.

Product differentiator:
  User → defines intent / goal (natural language)
  Agent → decides when / how / whether to send (this module)
  Agent → observes responses (future: conversation history as context)
  Agent → adapts behavior (future: tune from feedback)
"""

import json
import os
from dataclasses import dataclass
from typing import Optional

from openai import OpenAI


@dataclass
class ScheduledMessage:
    """Structured representation of user intent (agent-decided message, timing, and rules).

    Richer intent: supports conditional triggers (e.g. no_reply), action types (generate_followup),
    and tone, in addition to simple delay/repeat.
    """

    message: str
    contact_alias: str  # e.g. "wife", "mom", or "self" for reminder-to-self
    delay_seconds: Optional[int] = None  # 0 or None = send now; > 0 = delay in seconds
    scheduled_time: Optional[str] = None  # ISO format if specific time given
    raw_input: str = ""
    repeat_interval_seconds: Optional[int] = None  # e.g. 3 = every 3 seconds
    repeat_duration_seconds: Optional[int] = None  # e.g. 180 = for 3 minutes total
    repeat_stop_on_recipient_reply: bool = False  # true only when user said "until they accept/reply" etc.
    # Richer intent (conditional rules)
    trigger: str = "immediate"  # "immediate" | "scheduled" | "no_reply" | "reply_received"
    trigger_duration_seconds: Optional[int] = None  # for no_reply: wait this long (e.g. 4h = 14400)
    action: str = "send_exact"  # "send_exact" | "generate_followup" | "remind_me"
    tone: Optional[str] = None  # "gentle" | "warm" | "formal" | "casual" | null


SYSTEM_PROMPT = """You parse user requests into a structured intent (message, when, to whom, and optional rules).

Extract:
1. message - The exact text to send, or a short hint if the user wants a generated follow-up (expand casual phrasing: "good night text" → "Good night! Sleep well ❤️").
2. contact_alias - Who to send to: wife, husband, mom, dad, john, etc.
3. delay_seconds - Seconds from now until send. "in an hour" → 3600, "in 30 minutes" → 1800, "in 4 hours" → 14400. Use 0 or null for "when a condition is met".
4. scheduled_time - If a specific datetime, ISO format. Otherwise null.
5. trigger - When to act: "immediate" (send now), "scheduled" (send at delay/scheduled_time), "no_reply" (if they don't reply within a duration), "reply_received" (when they reply). Use "no_reply" for phrases like "if she doesn't reply in 4 hours".
6. trigger_duration_seconds - For trigger "no_reply": how long to wait (e.g. "4 hours" → 14400, "30 min" → 1800). Otherwise null.
7. action - What to do: "send_exact" (send the message as-is), "generate_followup" (generate a follow-up message, use message as hint/topic), "remind_me" (reminder for self). Use "generate_followup" for "follow up", "send a follow-up", "ping them again".
8. tone - Optional: "gentle", "warm", "formal", "casual". Use for "follow up gently", "send something warm", etc. Otherwise null.

Examples:
- "Send good night to my wife in an hour" → trigger: "scheduled", delay_seconds: 3600, action: "send_exact", tone: null
- "If she doesn't reply in 4 hours, follow up gently" → trigger: "no_reply", trigger_duration_seconds: 14400, action: "generate_followup", tone: "gentle", message: "follow up"
- "Remind me to call mom in 2 hours" → contact_alias: "self", trigger: "scheduled", delay_seconds: 7200, action: "remind_me"

Return JSON: {"message": "...", "contact_alias": "...", "delay_seconds": N|null, "scheduled_time": null|"ISO", "trigger": "immediate"|"scheduled"|"no_reply"|"reply_received", "trigger_duration_seconds": N|null, "action": "send_exact"|"generate_followup"|"remind_me", "tone": null|"gentle"|"warm"|"formal"|"casual"}

Only return valid JSON, no markdown or explanation."""

SYSTEM_PROMPT_IN_APP = """You are an intent parser for an in-app chat. The user is in a 1:1 conversation with {other_username}. They express a goal or intent in natural language. Output the actual message text when action is send_exact; otherwise use message as a short hint.

1. message - The full text to send (for send_exact), or a short hint (for generate_followup). Expand shorthand: "bday wishes" → full birthday message, "thanks" → genuine thank-you. Never output the user's meta-instruction verbatim.
2. contact_alias - Use "{other_username}" for the other person, or "self" for reminder-to-self.
3. delay_seconds - 0 for now, or seconds from now. For trigger "no_reply", use 0 (timing is in trigger_duration_seconds).
4. scheduled_time - Specific datetime in ISO, or null.
5. repeat_interval_seconds / repeat_duration_seconds - For "every X for Y". null otherwise.
6. repeat_stop_on_recipient_reply - true only for "until they accept/reply". false for "every year" etc.
7. trigger - "immediate" | "scheduled" | "no_reply" | "reply_received". Use "no_reply" for "if she doesn't reply in X", "if no response in 4 hours", or behavioral goals like "don't let this go cold", "keep things warm".
8. trigger_duration_seconds - For trigger "no_reply": use a number only when the user gives a fixed time (e.g. "4 hours" → 14400). For behavioral intents like "don't let this go cold", "keep things warm but not clingy", leave null so the system uses adaptive timing from conversation history.
9. action - "send_exact" | "generate_followup" | "remind_me". Use "generate_followup" for "follow up", "follow up gently", "ping again", "don't let it go cold".
10. tone - "gentle" | "warm" | "formal" | "casual" | null. Use for "follow up gently", "something warm", "not clingy" → gentle.

Examples:
- "thanks!" → message: "Thanks!", trigger: "immediate", action: "send_exact", tone: null
- "If she doesn't reply in 4 hours, follow up gently" → trigger: "no_reply", trigger_duration_seconds: 14400, action: "generate_followup", tone: "gentle", message: "follow up"
- "Don't let this go cold" / "Keep things warm but not clingy" → trigger: "no_reply", trigger_duration_seconds: null, action: "generate_followup", tone: "gentle", message: "keep things warm"
- "send apology every 3 sec until she accepts" → repeat_interval_seconds: 3, repeat_duration_seconds: 180, repeat_stop_on_recipient_reply: true

Return JSON with all fields: message, contact_alias, delay_seconds, scheduled_time, repeat_interval_seconds, repeat_duration_seconds, repeat_stop_on_recipient_reply, trigger, trigger_duration_seconds, action, tone. Use null where not applicable.

Only return valid JSON, no markdown or explanation."""

EXPAND_MESSAGE_PROMPT = """You turn a user's chat instruction into the exact message text to send. The user is in a 1:1 chat and said something like "send bday wishes" or "tell them thanks" or "can you send something warm". Your job is to output ONLY the actual message text that should appear in the chat — the words the recipient will see. Do not output the user's instruction; output the expanded message.

Rules:
- "bday wishes" / "birthday wishes" / "send something warm" → a short, warm happy birthday message (e.g. "Happy Birthday! Wishing you a wonderful day filled with joy and warmth. Hope this year brings you everything you've been dreaming of! 🎂")
- "say thanks" / "thank them" → a genuine thank-you message
- "good night" / "good night text" → "Good night! Sleep well ❤️"
- If the user already wrote a direct message (e.g. "Hey, see you tomorrow"), output it as-is or lightly polish.
- Output nothing but the message text: no quotes, no "Message:", no explanation."""

GENERATE_FOLLOWUP_PROMPT = """You generate a short follow-up message for someone who didn't reply yet.

Context: The user asked to send a follow-up (hint: "{message_hint}") with a {tone} tone. Generate ONE short message that would work as a gentle nudge — no guilt, just friendly. Output only the message text, no quotes or explanation.
"""

GENERATE_FOLLOWUP_WITH_MEMORY_PROMPT = """You generate a short follow-up message for someone who didn't reply yet.

Context: The user asked to send a follow-up (hint: "{message_hint}") with a {tone} tone.
{memory_block}
Generate ONE short message that would work as a gentle nudge — no guilt, just friendly. Output only the message text, no quotes or explanation.
"""


def generate_followup_draft(
    message_hint: str,
    tone: str | None = None,
    memory_summary: str | None = None,
) -> str:
    """Generate a follow-up message draft using the LLM. Uses memory_summary to adapt tone when provided."""
    import os
    tone = (tone or "gentle").lower()
    if memory_summary and memory_summary.strip():
        memory_block = f"Past follow-up insight: {memory_summary.strip()}. Use this to adapt tone or style."
        prompt = GENERATE_FOLLOWUP_WITH_MEMORY_PROMPT.format(
            message_hint=message_hint[:200], tone=tone, memory_block=memory_block
        )
    else:
        prompt = GENERATE_FOLLOWUP_PROMPT.format(message_hint=message_hint[:200], tone=tone)
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
        return content if content else f"Just checking in — {message_hint or 'follow up'}?"
    except Exception:
        return f"Just checking in — {message_hint or 'follow up'}?"


def expand_message_for_in_app(user_instruction: str) -> str:
    """Turn a user instruction (e.g. 'send bday wishes - something warm') into the actual message text to send.
    Returns the expanded string, or the original if expansion fails.
    """
    if not (user_instruction or user_instruction.strip()):
        return user_instruction
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": EXPAND_MESSAGE_PROMPT},
                {"role": "user", "content": user_instruction.strip()},
            ],
            temperature=0.3,
        )
        content = (response.choices[0].message.content or "").strip()
        # Remove surrounding quotes if the model added them
        if len(content) >= 2 and content[0] == content[-1] and content[0] in '"\'':
            content = content[1:-1]
        return content if content else user_instruction.strip()
    except Exception:
        return user_instruction.strip()


def parse_request(user_input: str, conversation_context: Optional[dict] = None) -> ScheduledMessage:
    """Parse natural language into intent (message, when, to whom). Agent decides when/how to send.
    If conversation_context is provided (e.g. {"other_username": "alice"}), uses in-app prompt.
    """
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    if conversation_context and conversation_context.get("other_username"):
        system = SYSTEM_PROMPT_IN_APP.format(other_username=conversation_context["other_username"])
    else:
        system = SYSTEM_PROMPT

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_input},
        ],
        temperature=0,
    )
    content = response.choices[0].message.content.strip()
    # Handle markdown code blocks if present
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
        content = content.strip()
    data = json.loads(content)

    return ScheduledMessage(
        message=data["message"],
        contact_alias=data["contact_alias"],
        delay_seconds=data.get("delay_seconds"),
        scheduled_time=data.get("scheduled_time"),
        raw_input=user_input,
        repeat_interval_seconds=data.get("repeat_interval_seconds"),
        repeat_duration_seconds=data.get("repeat_duration_seconds"),
        repeat_stop_on_recipient_reply=bool(data.get("repeat_stop_on_recipient_reply")),
        trigger=((data.get("trigger") or "") or "immediate").strip() or "immediate",
        trigger_duration_seconds=data.get("trigger_duration_seconds"),
        action=((data.get("action") or "") or "send_exact").strip() or "send_exact",
        tone=data.get("tone") if data.get("tone") else None,
    )


SHOULD_STOP_REPEAT_PROMPT = """You decide whether to stop a repeating message based on the user's original intent.

The user set up a repeating message with this intent: "{raw_intent}"

The message being repeated: "{repeated_message}"
The recipient just replied: "{recipient_message}"
Recent conversation (oldest to newest): {recent_convo}

Only stop if the recipient's reply clearly satisfies the user's intent for stopping. Interpret the intent strictly:
- If the intent was to repeat "until they accept my apology" / "until she accepts": stop only when they explicitly accept, forgive, or say they're good. A generic "ty" or "thanks" or "ok" alone does NOT mean stop for an apology.
- If the intent was "birthday wishes every year" or similar ongoing/recurring with no "until" condition: do NOT stop on "ty" or "thanks" — that is just acknowledgment. Only stop if the intent implied a stop condition that is clearly satisfied (e.g. "until they reply" and they replied with substance).
- If the recipient asks to stop ("stop", "enough", "no more") or clearly rejects, you may stop regardless of intent.

Reply with exactly one word: yes or no."""


def should_stop_repeat(
    repeated_message: str,
    recipient_message: str,
    recent_messages: list[dict] | None = None,
    raw_intent: str | None = None,
) -> bool:
    """Ask the agent whether to stop the repeat given the recipient's reply and the user's original intent. Returns True only when the response satisfies the intent for stopping."""
    recent_convo = "[]"
    if recent_messages:
        parts = [
            f'{{"sender_id": {m.get("sender_id")}, "content": {json.dumps(m.get("content", ""))}}}'
            for m in (recent_messages[-10:] if len(recent_messages) > 10 else recent_messages)
        ]
        recent_convo = "[" + ", ".join(parts) + "]"
    intent_text = (raw_intent or "").strip() or "(no intent provided)"
    prompt = SHOULD_STOP_REPEAT_PROMPT.format(
        raw_intent=intent_text[:600],
        repeated_message=repeated_message[:500],
        recipient_message=recipient_message[:500],
        recent_convo=recent_convo,
    )
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        answer = (response.choices[0].message.content or "").strip().lower()
        return answer.startswith("yes") or answer == "y"
    except Exception:
        return False
