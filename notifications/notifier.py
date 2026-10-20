"""Delivery transports: SMTP e-mail and a generic WhatsApp-style webhook.

Credentials come from the environment only. Delivery failures are returned, not
raised, so one bad channel never stops the pipeline.
"""

from __future__ import annotations

import json
import re
import smtplib
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from email.message import EmailMessage

from .config import NotificationSettings


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


@dataclass
class NotificationResult:
    channel: str
    ok: bool
    detail: str = ""

    def as_dict(self) -> dict:
        return {"channel": self.channel, "ok": self.ok, "detail": self.detail}


def valid_email(address: str) -> bool:
    """Reject anything that is not a plain, single email address."""
    value = (address or "").strip()
    if not value or len(value) > 254 or "," in value or ";" in value:
        return False
    return bool(_EMAIL_RE.match(value))


def send_email_to(
    settings: NotificationSettings,
    recipients: list[str],
    subject: str,
    body: str,
    html: str | None = None,
) -> NotificationResult:
    """Send an e-mail to explicit recipients (e.g. a quotation requester).

    Addresses are validated and stripped of CR/LF so nothing supplied by a web
    form can inject extra headers or extra recipients.
    """
    if not settings.smtp_host or not settings.smtp_from:
        return NotificationResult("email", False, "SMTP not configured (need SMTP_HOST and SMTP_FROM)")

    cleaned = [a.strip() for a in recipients if valid_email(a)]
    if not cleaned:
        return NotificationResult("email", False, "no valid recipient email address")

    # Header injection guard.
    safe_subject = re.sub(r"[\r\n]+", " ", subject or "").strip()[:200]

    message = EmailMessage()
    message["Subject"] = safe_subject
    message["From"] = settings.smtp_from
    message["To"] = ", ".join(cleaned)
    message.set_content(body or "")
    if html:
        message.add_alternative(html, subtype="html")

    try:
        if settings.smtp_port == 465:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=context, timeout=20) as smtp:
                if settings.smtp_user:
                    smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
                if settings.smtp_use_tls:
                    smtp.starttls(context=ssl.create_default_context())
                if settings.smtp_user:
                    smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(message)
    except (smtplib.SMTPException, OSError) as exc:
        return NotificationResult("email", False, f"{type(exc).__name__}: {exc}")

    return NotificationResult("email", True, f"sent to {len(cleaned)} recipient(s)")


def _send_email(settings: NotificationSettings, subject: str, body: str) -> NotificationResult:
    """Send an operational alert to the configured ALERT_EMAILS list."""
    if not settings.smtp_ready:
        return NotificationResult("email", False, "SMTP not configured (need SMTP_HOST, SMTP_FROM, ALERT_EMAILS)")
    return send_email_to(settings, settings.alert_emails, subject, body)


def _send_whatsapp(settings: NotificationSettings, subject: str, body: str) -> NotificationResult:
    """POST to a WhatsApp (or generic webhook) provider.

    Supports CallMeBot, UltraMsg and a plain JSON endpoint, selected with
    NOTIFY_WEBHOOK_PROVIDER.
    """
    if not settings.webhook_ready:
        return NotificationResult("whatsapp", False, "NOTIFY_WEBHOOK_URL is not set")

    provider = settings.webhook_provider
    text = f"{subject}\n\n{body}"

    try:
        if provider == "callmebot":
            params = {"phone": settings.webhook_phone, "text": text, "apikey": settings.webhook_token}
            url = f"{settings.webhook_url}?{urllib.parse.urlencode(params)}"
            request = urllib.request.Request(url, method="GET")
        elif provider == "ultramsg":
            payload = {
                "to": settings.webhook_phone.lstrip("+"),
                "message": text,
                "token": settings.webhook_token,
            }
            request = urllib.request.Request(
                settings.webhook_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        else:
            headers = {"Content-Type": "application/json"}
            if settings.webhook_token:
                headers["Authorization"] = f"Bearer {settings.webhook_token}"
            request = urllib.request.Request(
                settings.webhook_url,
                data=json.dumps({"subject": subject, "message": body, "source": "my-team-escalations"}).encode("utf-8"),
                headers=headers,
                method="POST",
            )

        with urllib.request.urlopen(request, timeout=20) as response:
            status = response.getcode()
        if 200 <= status < 300:
            return NotificationResult("whatsapp", True, f"provider {provider} responded {status}")
        return NotificationResult("whatsapp", False, f"provider {provider} responded {status}")
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError) as exc:
        return NotificationResult("whatsapp", False, f"{type(exc).__name__}: {exc}")


class Notifier:
    """Fan a message out to channels, or send directly to chosen recipients."""

    def __init__(self, settings: NotificationSettings) -> None:
        self.settings = settings

    def send_email_to(
        self,
        recipients: list[str],
        subject: str,
        body: str,
        html: str | None = None,
    ) -> NotificationResult:
        """Send directly to specific recipients, ignoring ALERT_EMAILS.

        Used for transactional mail such as sending a quotation to the person
        who asked for it. Does not require NOTIFY_ENABLED, because it is part
        of delivering a service the customer asked for, not an alert.
        """
        return send_email_to(self.settings, recipients, subject, body, html)

    def send(self, subject: str, body: str) -> list[NotificationResult]:
        if not self.settings.enabled:
            return [NotificationResult("none", False, "notifications disabled (set NOTIFY_ENABLED=true)")]

        channels = self.settings.active_channels()
        if not channels:
            return [NotificationResult("none", False, "no notification channel is configured")]

        results: list[NotificationResult] = []
        for channel in channels:
            if channel == "email":
                results.append(_send_email(self.settings, subject, body))
            elif channel in ("whatsapp", "webhook"):
                results.append(_send_whatsapp(self.settings, subject, body))
        return results