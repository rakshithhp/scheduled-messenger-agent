"""Schedule messages to be sent at the right time."""

from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger

from .sender import send_sms
from .contacts import get_phone


class Scheduler:
    """Schedules and executes message sends."""

    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()

    def schedule_message(self, message: str, contact_alias: str, delay_seconds: int, on_sent_callback=None):
        """Schedule a message to be sent after delay_seconds."""
        phone = get_phone(contact_alias)
        if not phone:
            raise ValueError(
                f"Unknown contact '{contact_alias}'. Add them first with: python main.py add-contact {contact_alias} +1234567890"
            )

        def job():
            send_sms(phone, message)
            if on_sent_callback:
                on_sent_callback(message, contact_alias, phone)

        run_at = datetime.now() + timedelta(seconds=delay_seconds)

        self.scheduler.add_job(job, trigger=DateTrigger(run_date=run_at), id=f"msg_{contact_alias}_{run_at.timestamp()}")

    def shutdown(self):
        self.scheduler.shutdown(wait=False)
