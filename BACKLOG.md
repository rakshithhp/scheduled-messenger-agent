# Backlog

## Repeat stop based on intent (non-critical)

**Issue:** Repeating messages should stop when the recipient replies only when the user's intent included a stop condition (e.g. "until she accepts my apology"). Repeats that have no "until" (e.g. "birthday message every year") should never stop when the recipient says "ty" or similar.

**Current state:** Logic exists to:
- Store `repeat_stop_on_recipient_reply` from the parser and only register in `repeat_series` when true.
- Pass `raw_intent` to the agent when deciding whether to stop.
- Cancel remaining jobs when the agent says stop.

**Problem:** The behavior is still not correct in practice (e.g. yearly birthday repeat may still stop on "ty", or apology repeat may not stop when it should). Needs further debugging and/or prompt/schema tuning so that:
- "Apology every 3s until she accepts" → stop only when the recipient clearly accepts/forgives; "ty" alone should not stop.
- "Birthday every year" → "ty" or "thanks" must never stop the repeat.

**Related code:** `agent/parser.py` (`repeat_stop_on_recipient_reply`, `should_stop_repeat`), `app.py` (`repeat_series`, `check_repeat_stop_on_message`, `schedule_in_app_from_parsed`).

## Execute trigger=no_reply (follow-up when no response)

**Intent:** Parser now outputs richer intent: `trigger` (e.g. "no_reply"), `trigger_duration_seconds`, `action` ("generate_followup"), `tone` ("gentle"). Example: "If she doesn't reply in 4 hours, follow up gently" → `trigger: no_reply`, `trigger_duration_seconds: 14400`, `action: generate_followup`, `tone: gentle`.

**Backlog:** Implement execution for `trigger=no_reply`: after `trigger_duration_seconds`, check whether the recipient has replied in the conversation; if not, generate a follow-up message (using `action` and `tone`) and send it. This requires a scheduled job and a "generate follow-up" step (LLM or template) that respects `tone`.
