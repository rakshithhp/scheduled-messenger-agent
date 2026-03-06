"""APNs push notifications for iOS. Optional: set env vars to enable."""

import json
import os
import time
from pathlib import Path

from auth.db import get_conn

# APNS_KEY_ID, APNS_TEAM_ID, APNS_BUNDLE_ID, APNS_AUTH_KEY_PATH (path to .p8 file)
# Or APNS_AUTH_KEY_CONTENT (raw .p8 content) for AWS where file may not exist


def get_device_tokens(user_id: int, platform: str = "ios") -> list[str]:
    """Return list of device tokens for this user (e.g. for iOS)."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT device_token FROM device_tokens WHERE user_id = ? AND platform = ?",
        (user_id, platform),
    ).fetchall()
    return [r["device_token"] for r in rows if r["device_token"]]


def register_device_token(user_id: int, device_token: str, platform: str = "ios") -> None:
    """Register or update a device token for push notifications."""
    token = (device_token or "").strip()
    if not token:
        return
    conn = get_conn()
    conn.execute(
        """INSERT INTO device_tokens (user_id, device_token, platform)
           VALUES (?, ?, ?)
           ON CONFLICT (user_id, device_token) DO UPDATE SET created_at = datetime('now')""",
        (user_id, token, platform),
    )
    conn.commit()


def unregister_device_token(user_id: int, device_token: str) -> None:
    """Remove a device token (e.g. on logout)."""
    conn = get_conn()
    conn.execute(
        "DELETE FROM device_tokens WHERE user_id = ? AND device_token = ?",
        (user_id, (device_token or "").strip()),
    )
    conn.commit()


def send_apns_to_user(
    user_id: int,
    title: str,
    body: str,
    data: dict | None = None,
    badge: int | None = None,
) -> None:
    """
    Send APNs push to all registered iOS devices for this user.
    No-op if APNs is not configured (missing env vars).
    """
    tokens = get_device_tokens(user_id, platform="ios")
    if not tokens:
        return
    _send_apns(tokens, title=title, body=body, data=data or {}, badge=badge)


def _send_apns(
    device_tokens: list[str],
    title: str,
    body: str,
    data: dict,
    badge: int | None = None,
) -> None:
    """Send to APNs (HTTP/2). Requires APNS_KEY_ID, APNS_TEAM_ID, APNS_BUNDLE_ID, APNS_AUTH_KEY_PATH or APNS_AUTH_KEY_CONTENT."""
    key_id = os.environ.get("APNS_KEY_ID")
    team_id = os.environ.get("APNS_TEAM_ID")
    bundle_id = os.environ.get("APNS_BUNDLE_ID")
    key_path = os.environ.get("APNS_AUTH_KEY_PATH")
    key_content = os.environ.get("APNS_AUTH_KEY_CONTENT")
    if not all([key_id, team_id, bundle_id]) or not (key_path or key_content):
        return
    try:
        import jwt
        import httpx
    except ImportError:
        return
    raw_key = key_content
    if not raw_key and key_path:
        path = Path(key_path)
        if path.exists():
            raw_key = path.read_text()
    if not raw_key:
        return
    # JWT for APNs: ES256, kid, iss=team_id
    now = int(time.time())
    payload = {"iss": team_id, "iat": now, "exp": now + 3600}
    headers = {"alg": "ES256", "kid": key_id}
    try:
        token = jwt.encode(
            payload,
            raw_key,
            algorithm="ES256",
            headers=headers,
        )
        if hasattr(token, "decode"):
            token = token.decode("utf-8")
    except Exception:
        return
    host = "api.sandbox.push.apple.com" if os.environ.get("APNS_SANDBOX") == "1" else "api.push.apple.com"
    aps_payload = {
        "aps": {
            "alert": {"title": title, "body": body},
            "sound": "default",
        },
        **data,
    }
    if badge is not None:
        aps_payload["aps"]["badge"] = int(badge)
    body_bytes = json.dumps(aps_payload, ensure_ascii=False).encode("utf-8")
    with httpx.Client(http2=True) as client:
        for device_token in device_tokens:
            try:
                r = client.post(
                    f"https://{host}/3/device/{device_token}",
                    content=body_bytes,
                    headers={
                        "authorization": f"bearer {token}",
                        "apns-topic": bundle_id,
                        "apns-push-type": "alert",
                        "apns-priority": "10",
                        "content-type": "application/json",
                    },
                    timeout=10.0,
                )
                if r.status_code == 410 or r.status_code == 400:
                    # Token invalid; could remove from DB
                    pass
            except Exception:
                pass
