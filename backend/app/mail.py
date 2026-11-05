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


def welcome(to: str, name: str) -> bool:
    """Sent once when an account is created. Plain text, no tracking, no links that act on the account."""
    who = name.strip() or "there"
    return send(to, "Welcome to PAM", f"""Hi {who},

Your PAM register is open. You have a household of your own, empty and ready.

Start here:
1. Books: add a savings account or credit card.
2. Entries: write your first entry. PAM files it under a category straight away.
3. Budgets: set a monthly limit to see where you stand.

Sign in any time at {settings.app_url}

If you did not create this account, you can ignore this email.
Nobody can use it without your password or Google account.
""")


def password_changed(to: str) -> bool:
    """Security notice after a reset, so an unexpected reset does not go unnoticed."""
    return send(to, "Your PAM password was changed", f"""Your PAM password was just changed using a reset link.

If that was you, nothing more to do.
If it was not, reset it again right away at {settings.app_url}/forgot and check your email account's security.
""")
