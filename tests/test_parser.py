"""Unit tests for agent parser (parse_request, expand_message_for_in_app, should_stop_repeat)."""

from unittest.mock import patch, MagicMock

import pytest

from agent.parser import (
    ScheduledMessage,
    parse_request,
    expand_message_for_in_app,
    should_stop_repeat,
)


def _mock_openai_response(content: str):
    """Build a mock OpenAI response with the given message content."""
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    return mock_response


@patch("agent.parser.OpenAI")
def test_parse_request_returns_scheduled_message(mock_openai_class):
    """parse_request calls OpenAI and returns a ScheduledMessage with parsed fields."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_openai_response(
        '{"message": "Hello!", "contact_alias": "bob", "delay_seconds": 0, "scheduled_time": null, '
        '"repeat_interval_seconds": null, "repeat_duration_seconds": null, "repeat_stop_on_recipient_reply": false}'
    )

    result = parse_request("say hello to bob")

    assert isinstance(result, ScheduledMessage)
    assert result.message == "Hello!"
    assert result.contact_alias == "bob"
    assert result.delay_seconds == 0
    assert result.raw_input == "say hello to bob"
    assert result.repeat_interval_seconds is None
    assert result.repeat_duration_seconds is None
    assert result.repeat_stop_on_recipient_reply is False


@patch("agent.parser.OpenAI")
def test_parse_request_with_repeat_fields(mock_openai_class):
    """parse_request parses repeat_interval, repeat_duration, repeat_stop_on_recipient_reply from JSON."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_openai_response(
        '{"message": "Sorry!", "contact_alias": "nish", "delay_seconds": 0, "scheduled_time": null, '
        '"repeat_interval_seconds": 3, "repeat_duration_seconds": 180, "repeat_stop_on_recipient_reply": true}'
    )

    # Use no conversation_context so SYSTEM_PROMPT is used (no .format with JSON braces)
    result = parse_request("send apology every 3 sec until she accepts")

    assert result.message == "Sorry!"
    assert result.contact_alias == "nish"
    assert result.repeat_interval_seconds == 3
    assert result.repeat_duration_seconds == 180
    assert result.repeat_stop_on_recipient_reply is True


@patch("agent.parser.OpenAI")
def test_parse_request_with_trigger_no_reply_and_tone(mock_openai_class):
    """parse_request parses trigger=no_reply, trigger_duration_seconds, action=generate_followup, tone."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_openai_response(
        '{"message": "follow up", "contact_alias": "nish", "delay_seconds": 0, "scheduled_time": null, '
        '"repeat_interval_seconds": null, "repeat_duration_seconds": null, "repeat_stop_on_recipient_reply": false, '
        '"trigger": "no_reply", "trigger_duration_seconds": 14400, "action": "generate_followup", "tone": "gentle"}'
    )
    result = parse_request("If she doesn't reply in 4 hours, follow up gently")
    assert result.trigger == "no_reply"
    assert result.trigger_duration_seconds == 14400
    assert result.action == "generate_followup"
    assert result.tone == "gentle"
    assert result.message == "follow up"


@patch("agent.parser.OpenAI")
def test_parse_request_behavioral_intent_null_duration(mock_openai_class):
    """parse_request with behavioral intent (e.g. don't let go cold) has trigger_duration_seconds null."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_openai_response(
        '{"message": "keep things warm", "contact_alias": "nish", "delay_seconds": 0, "scheduled_time": null, '
        '"repeat_interval_seconds": null, "repeat_duration_seconds": null, "repeat_stop_on_recipient_reply": false, '
        '"trigger": "no_reply", "trigger_duration_seconds": null, "action": "generate_followup", "tone": "gentle"}'
    )
    result = parse_request("Don't let this go cold")
    assert result.trigger == "no_reply"
    assert result.trigger_duration_seconds is None
    assert result.action == "generate_followup"
    assert result.tone == "gentle"


@patch("agent.parser.OpenAI")
def test_parse_request_strips_markdown_code_block(mock_openai_class):
    """parse_request handles JSON wrapped in markdown code block."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_openai_response(
        '```json\n{"message": "Hi", "contact_alias": "alice", "delay_seconds": 0, '
        '"scheduled_time": null, "repeat_interval_seconds": null, "repeat_duration_seconds": null, '
        '"repeat_stop_on_recipient_reply": false}\n```'
    )

    result = parse_request("hi to alice")

    assert result.message == "Hi"
    assert result.contact_alias == "alice"


@patch("agent.parser.OpenAI")
def test_expand_message_for_in_app_returns_expanded(mock_openai_class):
    """expand_message_for_in_app returns LLM response as expanded message."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_openai_response(
        "Happy Birthday! Wishing you a wonderful day!"
    )

    result = expand_message_for_in_app("send bday wishes")

    assert result == "Happy Birthday! Wishing you a wonderful day!"


@patch("agent.parser.OpenAI")
def test_expand_message_for_in_app_strips_quotes(mock_openai_class):
    """expand_message_for_in_app strips surrounding quotes from response."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_openai_response('"Happy Birthday!"')

    result = expand_message_for_in_app("bday wishes")

    assert result == "Happy Birthday!"


def test_expand_message_for_in_app_empty_input():
    """expand_message_for_in_app returns empty string for empty input."""
    result = expand_message_for_in_app("")
    assert result == ""


@patch("agent.parser.OpenAI")
def test_expand_message_for_in_app_on_exception_returns_original(mock_openai_class):
    """expand_message_for_in_app returns original instruction when OpenAI raises."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_client.chat.completions.create.side_effect = Exception("API error")

    result = expand_message_for_in_app("send thanks")

    assert result == "send thanks"


@patch("agent.parser.OpenAI")
def test_should_stop_repeat_returns_true_when_yes(mock_openai_class):
    """should_stop_repeat returns True when model responds yes."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_openai_response("yes")

    result = should_stop_repeat("I'm sorry", "I forgive you", raw_intent="apology until she accepts")

    assert result is True


@patch("agent.parser.OpenAI")
def test_should_stop_repeat_returns_false_when_no(mock_openai_class):
    """should_stop_repeat returns False when model responds no."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_openai_response("no")

    result = should_stop_repeat("I'm sorry", "ty", raw_intent="apology until she accepts")

    assert result is False


@patch("agent.parser.OpenAI")
def test_should_stop_repeat_returns_true_for_y(mock_openai_class):
    """should_stop_repeat returns True when model responds single letter y."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_openai_response("y")

    result = should_stop_repeat("Sorry", "ok accepted", raw_intent="until accept")

    assert result is True


@patch("agent.parser.OpenAI")
def test_should_stop_repeat_on_exception_returns_false(mock_openai_class):
    """should_stop_repeat returns False when OpenAI raises."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_client.chat.completions.create.side_effect = Exception("API error")

    result = should_stop_repeat("Sorry", "forgiven", raw_intent="until accept")

    assert result is False
