"""Event engine: message_sent, message_received, timer_elapsed. Handlers are invoked when events are emitted."""

import threading
from typing import Callable, Any

# Event types
MESSAGE_SENT = "message_sent"
MESSAGE_RECEIVED = "message_received"
TIMER_ELAPSED = "timer_elapsed"

_handlers: list[tuple[str, Callable[..., Any]]] = []
_lock = threading.Lock()


def register_handler(event_type: str, handler: Callable[..., Any]) -> None:
    """Register a handler for an event type. Handler receives (event_type, payload)."""
    with _lock:
        _handlers.append((event_type, handler))


def emit(event_type: str, payload: dict) -> None:
    """Emit an event. All handlers registered for this event_type are invoked with (event_type, payload)."""
    with _lock:
        to_call = [(t, h) for t, h in _handlers if t == event_type]
    for _, handler in to_call:
        try:
            handler(event_type, payload)
        except Exception:
            pass  # log and continue in production


def clear_handlers() -> None:
    """Remove all handlers (e.g. for tests)."""
    with _lock:
        _handlers.clear()
