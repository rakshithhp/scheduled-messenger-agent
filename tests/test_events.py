"""Tests for the event engine (message_sent, message_received, timer_elapsed)."""

import pytest

from agent.events import (
    MESSAGE_SENT,
    MESSAGE_RECEIVED,
    TIMER_ELAPSED,
    register_handler,
    emit,
    clear_handlers,
)


@pytest.fixture(autouse=True)
def clear_events():
    """Clear all handlers before and after each test."""
    clear_handlers()
    yield
    clear_handlers()


def test_emit_invokes_registered_handler():
    """emit calls the handler registered for that event type."""
    received = []

    def handler(event_type: str, payload: dict):
        received.append((event_type, payload))

    register_handler(MESSAGE_SENT, handler)
    emit(MESSAGE_SENT, {"conversation_id": 1, "sender_id": 2, "message_id": 3})
    assert len(received) == 1
    assert received[0][0] == MESSAGE_SENT
    assert received[0][1]["conversation_id"] == 1
    assert received[0][1]["message_id"] == 3


def test_emit_does_not_invoke_other_event_handlers():
    """emit only calls handlers for the emitted event type."""
    sent_received = []
    timer_received = []

    register_handler(MESSAGE_SENT, lambda t, p: sent_received.append((t, p)))
    register_handler(TIMER_ELAPSED, lambda t, p: timer_received.append((t, p)))
    emit(MESSAGE_SENT, {"x": 1})
    assert len(sent_received) == 1
    assert len(timer_received) == 0


def test_emit_invokes_multiple_handlers_for_same_type():
    """emit calls all handlers registered for that event type."""
    calls = []

    register_handler(MESSAGE_RECEIVED, lambda t, p: calls.append(1))
    register_handler(MESSAGE_RECEIVED, lambda t, p: calls.append(2))
    emit(MESSAGE_RECEIVED, {})
    assert calls == [1, 2]


def test_clear_handlers_removes_all():
    """clear_handlers removes all registered handlers."""
    received = []
    register_handler(MESSAGE_SENT, lambda t, p: received.append(p))
    clear_handlers()
    emit(MESSAGE_SENT, {"a": 1})
    assert len(received) == 0


def test_handler_exception_does_not_break_emit():
    """If a handler raises, other handlers still run and emit completes."""
    ok_calls = []

    def failing(et: str, p: dict):
        raise ValueError("oops")

    register_handler(MESSAGE_SENT, failing)
    register_handler(MESSAGE_SENT, lambda t, p: ok_calls.append(p))
    emit(MESSAGE_SENT, {"x": 1})
    assert len(ok_calls) == 1
    assert ok_calls[0]["x"] == 1
