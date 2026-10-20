"""Human-in-the-loop notification pipeline.

Nothing in this package ever hardcodes a credential. Every secret is read from
the environment (see ``config.py`` and ``.env.example``).
"""

from .config import NotificationSettings, get_settings
from .escalations import (
    Escalation,
    build_campaign_escalation,
    build_lead_escalation,
    build_accounting_escalation,
)
from .notifier import Notifier, NotificationResult

__all__ = [
    "NotificationSettings",
    "get_settings",
    "Notifier",
    "NotificationResult",
    "Escalation",
    "build_campaign_escalation",
    "build_lead_escalation",
    "build_accounting_escalation",
]

# NOTE: ``run_once`` is deliberately not imported here. Doing so would make
# ``python -m notifications.worker`` import the module twice (once via this
# package, once via runpy) and emit a RuntimeWarning. Import it as
# ``from notifications.worker import run_once`` instead.