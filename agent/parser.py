"""Parse natural language requests into structured scheduled message tasks."""

import json
import os
from dataclasses import dataclass
from typing import Optional

from openai import OpenAI


@dataclass
class ScheduledMessage:
    """Structured representation of a scheduled message request."""

    message: str
    contact_alias: str  # e.g., "wife", "mom"
    delay_seconds: Optional[int] = None  # e.g., 3600 for "in an hour"
    scheduled_time: Optional[str] = None  # ISO format if specific time given
    raw_input: str = ""


SYSTEM_PROMPT = """You parse user requests for scheduling messages. Extract:
1. message - The exact text to send (expand casual phrasing: "good night text" → "Good night! Sleep well ❤️")
2. contact_alias - Who to send to as a short alias: wife, husband, mom, dad, john, etc.
3. delay_seconds - How many seconds from now until send. Parse:
   - "after an hour" / "in an hour" → 3600
   - "in 30 minutes" → 1800
   - "in 2 hours" → 7200
   - "in 5 minutes" → 300
   - "tomorrow at 9am" → calculate approx seconds (or use scheduled_time)
4. scheduled_time - If a specific datetime, ISO format. Otherwise null.

Return JSON: {"message": "...", "contact_alias": "...", "delay_seconds": N, "scheduled_time": null|"ISO"}

Only return valid JSON, no markdown or explanation."""


def parse_request(user_input: str) -> ScheduledMessage:
    """Parse natural language into a ScheduledMessage using an LLM."""
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
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
    )
