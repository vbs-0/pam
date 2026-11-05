"""Outbound mail over authenticated SMTP + STARTTLS (Gmail, SMTP2GO, anything on port 587/2525).

Never raises: a mail problem must not fail the request that asked for it. Unconfigured servers just log and skip."""
import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.config import settings

log = logging.getLogger("pam.mail")


def configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_user and settings.smtp_password and settings.mail_from)


def send(to: str, subject: str, body: str) -> bool:
    if not configured():
        log.warning("mail skipped (SMTP not configured): %s", subject)
        return False
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = f"PAM <{settings.mail_from}>", to, subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(msg)
        return True
    except (OSError, smtplib.SMTPException):
        log.exception("mail to %s failed", to)       # the address is not secret; the body (a link) is never logged
        return False
