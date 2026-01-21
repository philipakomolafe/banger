"""
Email utilities module - handles sending email notifications.
"""

import os
import smtplib
from email.message import EmailMessage


def send_email(subject: str, body: str) -> bool:
    """
    Send an email notification.
    
    Requires environment variables:
        - SMTP_HOST: SMTP server hostname
        - SMTP_PORT: SMTP server port (default: 587)
        - SMTP_USER: SMTP username
        - SMTP_PASS: SMTP password
        - TO_EMAIL: Recipient email address
    
    Args:
        subject: Email subject line
        body: Email body content
    
    Returns:
        True if email sent successfully, False otherwise
    """
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    pwd = os.environ.get("SMTP_PASS")
    to_addr = os.environ.get("TO_EMAIL")
    from_addr = os.environ.get("SMTP_USER", to_addr)

    if not all([host, port, user, pwd, to_addr, from_addr]):
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.set_content(body)

    with smtplib.SMTP(host, port) as s:
        s.starttls()
        s.login(user, pwd)
        s.send_message(msg)
    return True
