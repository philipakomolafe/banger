"""
Email utilities module - handles sending email notifications.
"""

import os
import resend
import logging
from dotenv import load_dotenv


# Load ENV vars.
load_dotenv()
logger = logging.getLogger(__name__)

resend.api_key = os.getenv("RESEND_API_KEY")


def send_email(subject: str, body: str, to_email: str | None = None) -> bool:
    """
    Send email using Resend service.
    """

    # provided only for registered ussers.
    to_addr = to_email or os.environ.get("TO_EMAIL")
    from_addr = os.environ.get("FROM_USER")

    if not all([to_addr, from_addr]):
        logger.error("Email addresses not configured properly.")
        return False
    try:
        params = {
            "from": from_addr,
            "to": to_addr,
            "subject": subject,
            "html": body
        }
        resend.Emails.send(params)
        return True
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False
