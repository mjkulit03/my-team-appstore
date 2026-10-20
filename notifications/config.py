"""Configuration for notifications and the control panel.

Every value comes from the environment. There are no default secrets, and the
control panel stays locked unless a password is explicitly supplied, so a
misconfigured deploy fails closed rather than exposing itself.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

TRUTHY = {"1", "true", "yes", "on"}


def load_dotenv(path: str | Path = ".env", override: bool = False) -> int:
    """Load KEY=VALUE pairs from a .env file into os.environ.

    Deliberately dependency-free. Real environment variables (CI secrets, shell
    exports) always win unless ``override`` is True, so a deploy can never be
    surprised by a stray file. Returns the number of values loaded.
    """
    env_path = Path(path)
    if not env_path.is_file():
        return 0

    loaded = 0
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.lower().startswith("export "):
            line = line[7:].lstrip()
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if not key:
            continue
        if override or key not in os.environ:
            os.environ[key] = value
            loaded += 1
    return loaded


# Populate os.environ as early as possible so every other module (auth, the
# API routers, the worker) sees the same values.
load_dotenv()


def _flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in TRUTHY


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _csv(name: str) -> list[str]:
    raw = os.getenv(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class NotificationSettings:
    """Resolved notification configuration.

    ``secret_values`` is used for masking so secrets never reach logs or the
    API responses.
    """

    enabled: bool = False
    channels: list[str] = field(default_factory=list)

    # SMTP / e-mail
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True
    alert_emails: list[str] = field(default_factory=list)

    # Generic webhook (WhatsApp providers, Slack, Teams, ...)
    webhook_url: str = ""
    webhook_token: str = ""
    webhook_provider: str = "generic"
    webhook_phone: str = ""

    # Escalation thresholds (in the base currency, PHP by default)
    lead_value_threshold: float = 150000.0
    accounting_anomaly_threshold: float = 50000.0

    # Control panel
    panel_password: str = ""
    session_secret: str = ""

    # Storage
    data_dir: str = "var"

    def mask(self, value: str) -> str:
        """Return a safe, non-reversible preview of a secret."""
        if not value:
            return ""
        return f"{'*' * 4}{value[-2:]}" if len(value) > 2 else "**"

    @property
    def smtp_ready(self) -> bool:
        return bool(self.smtp_host and self.smtp_from and self.alert_emails)

    @property
    def webhook_ready(self) -> bool:
        return bool(self.webhook_url)

    @property
    def panel_enabled(self) -> bool:
        """The panel only opens when a password is explicitly configured."""
        return bool(self.panel_password)

    def active_channels(self) -> list[str]:
        """Channels that are both selected and actually configured."""
        chosen = set(self.channels)
        result = []
        if "email" in chosen and self.smtp_ready:
            result.append("email")
        if ("whatsapp" in chosen or "webhook" in chosen) and self.webhook_ready:
            result.append("whatsapp" if "whatsapp" in chosen else "webhook")
        return result

    def public_status(self) -> dict:
        """A redacted view safe to expose in the UI or API."""
        return {
            "enabled": self.enabled,
            "channels": self.active_channels(),
            "requested_channels": self.channels,
            "email": {
                "configured": self.smtp_ready,
                "host": self.smtp_host,
                "port": self.smtp_port,
                "from": self.smtp_from,
                "recipients": self.alert_emails,
            },
            "webhook": {
                "configured": self.webhook_ready,
                "provider": self.webhook_provider,
                "url": self.mask(self.webhook_url),
                "token": self.mask(self.webhook_token),
            },
            "panel_enabled": self.panel_enabled,
            "thresholds": {
                "lead_value": self.lead_value_threshold,
                "accounting_anomaly": self.accounting_anomaly_threshold,
            },
        }


def get_settings() -> NotificationSettings:
    """Build settings from the current environment."""
    raw_channels = [c.lower() for c in _csv("NOTIFY_CHANNELS")] or ["email"]
    return NotificationSettings(
        enabled=_flag("NOTIFY_ENABLED", False),
        channels=raw_channels,
        smtp_host=os.getenv("SMTP_HOST", "").strip(),
        smtp_port=_int("SMTP_PORT", 587),
        smtp_user=os.getenv("SMTP_USER", "").strip(),
        smtp_password=os.getenv("SMTP_PASSWORD", ""),
        smtp_from=os.getenv("SMTP_FROM", "").strip(),
        smtp_use_tls=_flag("SMTP_USE_TLS", True),
        alert_emails=_csv("ALERT_EMAILS"),
        webhook_url=os.getenv("NOTIFY_WEBHOOK_URL", "").strip(),
        webhook_token=os.getenv("NOTIFY_WEBHOOK_TOKEN", ""),
        webhook_provider=os.getenv("NOTIFY_WEBHOOK_PROVIDER", "generic").strip().lower(),
        webhook_phone=os.getenv("NOTIFY_WEBHOOK_PHONE", "").strip(),
        lead_value_threshold=_float("LEAD_VALUE_THRESHOLD", 150000.0),
        accounting_anomaly_threshold=_float("ACCOUNTING_ANOMALY_THRESHOLD", 50000.0),
        panel_password=os.getenv("CONTROL_PANEL_PASSWORD", ""),
        session_secret=os.getenv("SESSION_SECRET", ""),
        data_dir=os.getenv("DATA_DIR", "var"),
    )