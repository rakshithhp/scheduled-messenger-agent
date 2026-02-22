"""Send messages via Twilio or Amazon SNS."""

import os


def _get_backend() -> str:
    """Return the active messaging backend: 'twilio' or 'sns'."""
    return (os.getenv("MESSAGE_BACKEND") or "twilio").lower()


def _send_via_twilio(to_phone: str, body: str) -> bool:
    """Send an SMS via Twilio. Returns True on success."""
    from twilio.rest import Client

    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    from_phone = os.getenv("TWILIO_PHONE_NUMBER")

    if not all([sid, token, from_phone]):
        raise ValueError(
            "Twilio credentials missing. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, "
            "TWILIO_PHONE_NUMBER in .env"
        )

    client = Client(sid, token)
    client.messages.create(to=to_phone, from_=from_phone, body=body)
    return True


def _send_via_sns(to_phone: str, body: str) -> bool:
    """Send an SMS via Amazon SNS. Returns True on success."""
    import boto3

    region = os.getenv("AWS_REGION", "us-east-1")

    client = boto3.client("sns", region_name=region)
    client.publish(
        PhoneNumber=to_phone,
        Message=body,
        MessageAttributes={
            "AWS.SNS.SMS.SMSType": {
                "DataType": "String",
                "StringValue": "Transactional",
            }
        },
    )
    return True


def send_sms(to_phone: str, body: str) -> bool:
    """
    Send an SMS via the configured backend (Twilio or Amazon SNS).
    Set MESSAGE_BACKEND=twilio or MESSAGE_BACKEND=sns in .env
    Defaults to Twilio if not set.
    """
    backend = _get_backend()
    if backend == "sns":
        return _send_via_sns(to_phone, body)
    if backend == "twilio":
        return _send_via_twilio(to_phone, body)
    raise ValueError(
        f"Unknown MESSAGE_BACKEND='{backend}'. Use 'twilio' or 'sns'."
    )
