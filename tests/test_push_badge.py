"""Tests for APNs badge computation on new messages."""

from unittest.mock import patch


def test_push_message_to_ws_calls_apns_with_badge():
    # Import inside test so conftest env vars are set first.
    from app import push_message_to_ws

    msg = {"id": 123, "sender_id": 1, "content": "hi", "created_at": "now"}
    conversation_id = 99

    with patch("app.get_participant_ids", return_value=[1, 2]), patch(
        "messaging.models.get_total_unread_count", return_value=7
    ), patch("agent.push.send_apns_to_user") as send_apns:
        push_message_to_ws(msg, conversation_id)

    # Should notify recipient (2) but not sender (1)
    assert send_apns.call_count == 1
    _, kwargs = send_apns.call_args
    assert kwargs["badge"] == 7
    assert kwargs["data"]["conversation_id"] == conversation_id

