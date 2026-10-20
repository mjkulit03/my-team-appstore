"""The multi-agent quotation pipeline.

A customer asks for a quote or a demo, and the AI workforce handles it:

    1. Marketing AI  — qualifies the request, picks the tone and the angle
    2. Sales AI       — assembles the priced quotation and the cover note
    3. Accounting AI  — checks margin and discount; approves or escalates
    4. Delivery       — e-mails the quotation to the requester, alerts ops

Each stage records what it decided so the transcript is visible in the control
panel. Nothing is ever sent to a customer unless Accounting has cleared the
price, and any quote that breaches policy raises a human escalation.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import currency
import quotation as quote_lib
import store
from agents import run_marketing_agent, run_sales_agent
from notifications.config import NotificationSettings, get_settings
from notifications.escalations import render_notification
from notifications.notifier import Notifier, valid_email

STAGES = ("marketing", "sales", "accounting", "delivery")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def discount_approval_threshold() -> Decimal:
    raw = os.getenv("QUOTE_DISCOUNT_APPROVAL_PCT", "15").strip()
    try:
        return Decimal(raw)
    except Exception:  # noqa: BLE001
        return Decimal("15")


def margin_floor() -> Decimal:
    raw = os.getenv("QUOTE_MARGIN_FLOOR_PCT", "45").strip()
    try:
        return Decimal(raw)
    except Exception:  # noqa: BLE001
        return Decimal("45")


def _stage(name: str, agent: str, summary: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"stage": name, "agent": agent, "summary": summary, "data": data or {}, "at": _now()}


def run_quotation_pipeline(
    product: dict[str, Any],
    customer: dict[str, Any],
    *,
    seats: int = 1,
    term_months: int = 12,
    discount_pct: float = 0.0,
    support: bool = False,
    send_email: bool = True,
    settings: NotificationSettings | None = None,
) -> dict[str, Any]:
    """Run the four-stage pipeline and return the transcript plus the quote.

    Returns a dict with ``quotation``, ``transcript``, ``status`` and ``email``.
    ``status`` is one of ``sent``, ``approved_not_sent``, ``needs_approval``,
    ``no_email`` or ``failed``.

    Raises:
        ValueError: for an invalid customer or product.
    """
    settings = settings or get_settings()
    transcript: list[dict[str, Any]] = []

    name = (customer.get("name") or "").strip()
    email = (customer.get("email") or "").strip()
    organisation = (customer.get("organisation") or "").strip()
    message = (customer.get("message") or "").strip()
    if not name:
        raise ValueError("customer name is required")
    if not email:
        raise ValueError("customer email is required")

    # ---------------------------------------------------------- 1. Marketing
    marketing = run_marketing_agent(
        product_description=product["description"],
        product_name=product["name"],
        tone="confident",
    )
    angle = f"{marketing['detected_audience']} running {product['name'].lower()}"
    transcript.append(
        _stage(
            "intake",
            "Marketing AI",
            f"Qualified the request as {marketing['detected_category']}; leading with "
            f"{angle}.",
            {
                "detected_category": marketing["detected_category"],
                "detected_audience": marketing["detected_audience"],
                "keywords": marketing["keywords"][:5],
            },
        )
    )

    # -------------------------------------------------------------- 2. Sales
    quote = quote_lib.build_quotation(
        product,
        {"name": name, "email": email, "organisation": organisation},
        seats=seats,
        term_months=term_months,
        discount_pct=discount_pct,
        support=support,
    )

    outreach = run_sales_agent(
        target_customer_type=product["audience"],
        product_name=product["name"],
        offer=(
            f"Your quotation {quote.reference} is ready — {quote.seats} seat"
            f"{'s' if quote.seats != 1 else ''} for {quote.term_months} months at "
            f"{quote_lib.money(quote.total, quote.currency)}."
        ),
        variants=1,
    )
    cover = outreach["emails"][0]["body"] if outreach["emails"] else ""

    note = (
        f"Hi {name.split()[0]},\n\n"
        f"Thank you for your interest in {product['name']}. Here is your quotation "
        f"({quote.reference}), covering {quote.seats} seat"
        f"{'s' if quote.seats != 1 else ''} over {quote.term_months} months.\n\n"
        f"{cover}\n\n"
        f"The quotation is valid until {quote.valid_until}. Reply to this e-mail and we "
        f"will walk you through it."
    )

    transcript.append(
        _stage(
            "pricing",
            "Sales AI",
            f"Built quotation {quote.reference} for {quote.seats} seat(s) over "
            f"{quote.term_months} months: {quote_lib.money(quote.total, quote.currency)} total.",
            {"reference": quote.reference, "total": float(quote.total), "currency": quote.currency},
        )
    )

    # --------------------------------------------------------- 3. Accounting
    margin = quote_lib.gross_margin(quote, product)
    discount_limit = discount_approval_threshold()
    floor = margin_floor()

    breaches: list[str] = []
    if Decimal(str(discount_pct or 0)) > discount_limit:
        breaches.append(
            f"discount of {quote_lib.pct(discount_pct)}% exceeds the "
            f"{quote_lib.pct(discount_limit)}% approval limit"
        )
    if margin < floor:
        breaches.append(
            f"gross margin {quote_lib.pct(margin)}% is below the {quote_lib.pct(floor)}% floor"
        )

    approved = not breaches
    transcript.append(
        _stage(
            "pricing_check",
            "Accounting AI",
            (
                f"Margin {quote_lib.pct(margin)}% (floor {quote_lib.pct(floor)}%), "
                f"discount {quote_lib.pct(discount_pct)}% (limit {quote_lib.pct(discount_limit)}%). "
                + ("Price approved." if approved else "Held for approval: " + "; ".join(breaches))
            ),
            {
                "margin_pct": float(margin),
                "floor_pct": float(floor),
                "discount_pct": discount_pct,
                "discount_limit_pct": float(discount_limit),
                "approved": approved,
                "breaches": breaches,
            },
        )
    )

    record = store.create_quotation(
        product_slug=product["slug"],
        product_name=product["name"],
        customer={"name": name, "email": email, "organisation": organisation, "message": message},
        quotation=quote.as_dict(),
        pricing_check={
            "margin_pct": float(margin),
            "floor_pct": float(floor),
            "discount_pct": discount_pct,
            "discount_limit_pct": float(discount_limit),
            "approved": approved,
            "breaches": breaches,
        },
        transcript=transcript,
        status="pending_email",
        email_sent=False,
    )

    if not approved:
        # A pricing breach is the most specific reason, so it wins over the
        # generic high-value rule even when the value also trips it.
        from notifications.escalations import Escalation

        escalation = Escalation(
            kind="pricing_approval",
            severity="high",
            title=f"Pricing needs approval: {product['name']}",
            summary="; ".join(breaches).capitalize(),
            details={
                "quotation_id": record["id"],
                "reference": quote.reference,
                "customer": name,
                "organisation": organisation,
                "email": email,
                "total": float(quote.total),
                "currency": quote.currency,
                "breaches": breaches,
                "requested_at": _now(),
                "decision_url": f"/control/quotations/{record['id']}",
            },
        )
        if float(quote.total) >= settings.lead_value_threshold:
            escalation.severity = "critical"
            escalation.details["also_high_value"] = True

        queued = store.create_escalation(**escalation.as_dict())
        store.update_quotation(record["id"], status="needs_approval", escalation_id=queued["id"])
        record["status"] = "needs_approval"
        record["escalation_id"] = queued["id"]
        record["pricing_check"]["escalation_id"] = queued["id"]

        # Ops still get told, even though the customer does not.
        subject, body = render_notification(escalation)
        alert = Notifier(settings).send(subject, body)
        transcript.append(
            _stage(
                "delivery",
                "Delivery",
                "Held the quotation for a human decision and alerted operations. "
                "Nothing was sent to the customer.",
                {"alert_results": [r.as_dict() for r in alert]},
            )
        )
        return {
            "status": "needs_approval",
            "quotation": quote.as_dict(),
            "quotation_id": record["id"],
            "transcript": transcript,
            "email": {"sent": False, "reason": "waiting for human approval"},
        }

    # ----------------------------------------------------------- 4. Delivery
    if not send_email:
        store.update_quotation(record["id"], status="approved_not_sent")
        transcript.append(_stage("delivery", "Delivery", "Draft ready; e-mail suppressed by caller."))
        return {
            "status": "approved_not_sent",
            "quotation": quote.as_dict(),
            "quotation_id": record["id"],
            "transcript": transcript,
            "email": {"sent": False, "reason": "send_email=False"},
        }

    if not valid_email(email):
        store.update_quotation(record["id"], status="no_email")
        transcript.append(_stage("delivery", "Delivery", f"'{email}' is not a valid e-mail address."))
        return {
            "status": "no_email",
            "quotation": quote.as_dict(),
            "quotation_id": record["id"],
            "transcript": transcript,
            "email": {"sent": False, "reason": "invalid recipient address"},
        }

    subject = f"Quotation {quote.reference} — {product['name']}"
    result = Notifier(settings).send_email_to(
        [email],
        subject,
        quote_lib.render_text(quote, note),
        html=quote_lib.render_html(quote, note),
    )

    if result.ok:
        store.update_quotation(record["id"], status="sent", email_sent=True, email_detail=result.detail)
        transcript.append(
            _stage("delivery", "Delivery", f"E-mailed the quotation to {email}.", {"detail": result.detail})
        )
        status = "sent"
    else:
        store.update_quotation(record["id"], status="failed", email_detail=result.detail)
        transcript.append(
            _stage("delivery", "Delivery", f"Could not send to {email}: {result.detail}", {"detail": result.detail})
        )
        status = "failed"

    return {
        "status": status,
        "quotation": quote.as_dict(),
        "quotation_id": record["id"],
        "transcript": transcript,
        "email": {"sent": result.ok, "to": email, "detail": result.detail},
    }