"""Sending mail, and being honest when there is nowhere to send it.

Two modes, chosen by whether ``SMTP_HOST`` is set:

* **smtp** - a real message over SMTP.
* **outbox** - no mail server is configured, so the message is written to the
  log and to ``data/outbox/`` instead.

The outbox mode exists because signup has to be demonstrable without anyone
handing this prototype a mailbox password. What it must never do is *look*
like it sent an email. Every send returns which mode ran, the API passes that
back, and the UI says "no mail server is configured - your code is in the
server log" rather than "check your inbox" for a message that will never
arrive.
"""

from __future__ import annotations

import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Literal

from app.core.config import BACKEND_ROOT, settings
from app.core.logging_config import get_logger
from app.utils.helpers import utcnow

logger = get_logger("app.email")

DeliveryMode = Literal["smtp", "outbox"]


@dataclass
class DeliveryResult:
    """What actually happened to a message."""

    mode: DeliveryMode
    recipient: str
    detail: str

    @property
    def delivered_externally(self) -> bool:
        return self.mode == "smtp"


class EmailDeliveryError(RuntimeError):
    """Raised when a configured SMTP server refused or could not be reached."""


def outbox_dir() -> Path:
    raw = Path(settings.MAIL_OUTBOX_PATH)
    return raw if raw.is_absolute() else (BACKEND_ROOT / raw)


def _write_to_outbox(recipient: str, subject: str, body: str) -> DeliveryResult:
    # The log is the authoritative fallback; the file is a convenience. Writing
    # it can fail for reasons that have nothing to do with the signup - a
    # read-only volume, a full disk, a path the OS rejects - and none of those
    # are a reason to fail the request when the code has already been logged.
    path: Path | None = None
    try:
        directory = outbox_dir()
        directory.mkdir(parents=True, exist_ok=True)
        stamp = utcnow().strftime("%Y%m%dT%H%M%S%f")
        safe_recipient = "".join(
            ch if ch.isalnum() or ch in "@.-_" else "_" for ch in recipient
        )[:64]
        path = directory / f"{stamp}-{safe_recipient}.txt"
        path.write_text(
            f"To: {recipient}\nSubject: {subject}\nWritten-At: {utcnow().isoformat()}\n\n{body}\n",
            encoding="utf-8",
        )
    except OSError:
        logger.exception("Could not write the outbox copy for %s", recipient)
        path = None

    # Logged at WARNING, not INFO: a one-time code sitting in a log file is a
    # real (if deliberate) weakness, and it should be visible as one.
    logger.warning(
        "No SMTP server configured - email for %s written to %s instead of being sent",
        recipient,
        path or "the log only",
    )
    logger.warning("---- message for %s ----\n%s", recipient, body)
    return DeliveryResult(
        mode="outbox", recipient=recipient, detail=str(path) if path else "log only"
    )


def _send_over_smtp(recipient: str, subject: str, body: str) -> DeliveryResult:
    message = EmailMessage()
    message["From"] = settings.SMTP_FROM
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP(
            settings.SMTP_HOST, settings.SMTP_PORT, timeout=settings.SMTP_TIMEOUT_SECONDS
        ) as server:
            server.ehlo()
            if settings.SMTP_USE_TLS:
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
            if settings.SMTP_USERNAME:
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.send_message(message)
    except (smtplib.SMTPException, OSError, ssl.SSLError) as exc:
        # Deliberately not falling back to the outbox. A configured mail
        # server that is failing is an incident; quietly writing the code to
        # a file instead would hide it and leave the user waiting for an
        # email nobody is going to send.
        logger.exception("SMTP delivery to %s failed", recipient)
        raise EmailDeliveryError(
            "The mail server could not be reached, so the code was not sent. "
            "Try again shortly."
        ) from exc

    logger.info("Sent '%s' to %s via %s", subject, recipient, settings.SMTP_HOST)
    return DeliveryResult(mode="smtp", recipient=recipient, detail=settings.SMTP_HOST)


def send(recipient: str, subject: str, body: str) -> DeliveryResult:
    """Deliver a message, or record it locally when no server is configured."""
    if settings.smtp_configured:
        return _send_over_smtp(recipient, subject, body)
    return _write_to_outbox(recipient, subject, body)


def send_verification_code(recipient: str, display_name: str, code: str) -> DeliveryResult:
    """Email a signup verification code."""
    body = (
        f"Hello {display_name},\n\n"
        f"Your KONE ELEVATE verification code is:\n\n"
        f"    {code}\n\n"
        f"It expires in {settings.OTP_TTL_MINUTES} minutes and can be used once.\n\n"
        "If you did not create this account, you can ignore this message - the\n"
        "account cannot be used until this code is entered.\n\n"
        "--\n"
        "KONE ELEVATE Component Passport (prototype).\n"
        "An independent student project, not affiliated with KONE Corporation.\n"
    )
    return send(recipient, "Your KONE ELEVATE verification code", body)
