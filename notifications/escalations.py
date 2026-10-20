"""Rules that decide when an AI employee must hand work to a human.

The AI workforce drafts; humans publish, commit and pay. Each builder returns an
``Escalation`` or ``None`` when the work can proceed unattended.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .config import NotificationSettings

# Products in these categories touch regulated, biometric or clinical data.
# AI-generated public copy for them is always held for human approval.
SENSITIVE_CATEGORIES = {
    "Healthcare Inventory",
    "Education & Attendance",
    "Time & Attendance",
}


@dataclass
class Escalation:
    kind: str
    severity: str
    title: str
    summary: str
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "severity": self.severity,
            "title": self.title,
            "summary": self.summary,
            "details": self.details,
        }


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_campaign_escalation(
    product: dict[str, Any],
    marketing: dict[str, Any],
    settings: NotificationSettings,
) -> Escalation | None:
    """Hold a marketing campaign for approval before it is published.

    Always escalates for sensitive categories, and otherwise when the generated
    copy was materially truncated (a strong sign the source description is thin).
    """
    category = product.get("category", "")
    posts = marketing.get("posts", [])

    truncated = [p for p in posts if p.get("truncated")]
    reasons = []
    if category in SENSITIVE_CATEGORIES:
        reasons.append(f"{category} data is regulated, so public claims need sign-off")
    if truncated:
        reasons.append(f"{len(truncated)} post(s) were truncated for length, check the copy still reads well")

    if not reasons:
        return None

    return Escalation(
        kind="campaign_approval",
        severity="high" if category in SENSITIVE_CATEGORIES else "medium",
        title=f"Marketing copy awaiting approval: {product.get('name')}",
        summary="; ".join(reasons),
        details={
            "product_slug": product.get("slug"),
            "product_name": product.get("name"),
            "category": category,
            "posts": posts,
            "strategy": marketing.get("strategy", []),
            "reasons": reasons,
            "requested_at": _stamp(),
            "decision_url": f"/control/campaigns/{product.get('slug')}",
        },
    )


def build_lead_escalation(lead: dict[str, Any], settings: NotificationSettings) -> Escalation | None:
    """Escalate a high-value lead for a human sales decision."""
    value = float(lead.get("estimated_value") or 0)
    if value < settings.lead_value_threshold:
        return None

    who = (lead.get("contact_name") or "").strip() or "A prospect"
    org = (lead.get("organisation") or "").strip()
    where = f" at {org}" if org else ""

    return Escalation(
        kind="high_value_lead",
        severity="high" if value >= settings.lead_value_threshold * 2 else "medium",
        title=f"High-value lead: {lead.get('product_name')}",
        summary=(
            f"{who}{where} is worth {value:,.0f}, above the "
            f"{settings.lead_value_threshold:,.0f} threshold. "
            "A human should decide on pricing and whether to discount."
        ),
        details={
            "lead_id": lead.get("id"),
            "product_slug": lead.get("product_slug"),
            "product_name": lead.get("product_name"),
            "contact_name": lead.get("contact_name"),
            "organisation": lead.get("organisation"),
            "email": lead.get("email"),
            "estimated_value": value,
            "threshold": settings.lead_value_threshold,
            "requested_at": _stamp(),
            "decision_url": f"/control/leads/{lead.get('id')}",
        },
    )


def build_accounting_escalation(report: dict[str, Any], settings: NotificationSettings) -> Escalation | None:
    """Escalate a critical accounting alert or a large unexplained movement."""
    totals = report.get("totals", {}) or {}
    alerts = report.get("alerts", []) or []

    critical = [a for a in alerts if a.get("level") == "critical"]
    net = float(totals.get("net") or 0.0)
    threshold = settings.accounting_anomaly_threshold

    reasons = [f"{a.get('code')}: {a.get('message')}" for a in critical]
    if net <= -threshold:
        reasons.append(f"net loss of {abs(net):,.2f} exceeds the {threshold:,.2f} anomaly threshold")

    if not reasons:
        return None

    return Escalation(
        kind="accounting_anomaly",
        severity="critical" if net <= -threshold else "high",
        title="Accounting anomaly needs review",
        summary="; ".join(reasons[:3]),
        details={
            "totals": totals,
            "alerts": alerts,
            "reasons": reasons,
            "requested_at": _stamp(),
            "decision_url": "/control/accounting",
        },
    )


def render_notification(escalation: Escalation) -> tuple[str, str]:
    """Format an escalation as an e-mail subject and body."""
    subject = f"[{escalation.severity.upper()}] {escalation.title}"
    lines = [
        escalation.summary,
        "",
        f"Type      : {escalation.kind}",
        f"Severity  : {escalation.severity}",
        f"Raised at : {_stamp()}",
        "",
        "This needs a human decision. Review it in the control panel:",
        escalation.details.get("decision_url", "/control"),
    ]
    return subject, "\n".join(lines)