"""Quotation building.

Turns a product inquiry into a priced, numbered, VAT-compliant quotation that can
be emailed to the requester.

Money model: catalog prices are **VAT-inclusive**, which is how software is
normally quoted in the Philippines. The quotation therefore shows the VAT
portion *inside* the total rather than adding it on top, so the number the
customer agrees to is the number on the quote.

Amounts use :class:`~decimal.Decimal` throughout, so cent rounding is exact.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

import currency

CENTS = Decimal("0.01")
DEFAULT_VAT_RATE = Decimal("0.12")  # Philippines standard output VAT
DEFAULT_VALIDITY_DAYS = 30
SUPPORT_RATE = Decimal("0.15")  # optional annual support, % of subscription

# Offline / on-premise deployments. Contract is paid in two halves, then the
# annual maintenance retainer is invoiced on top of the contract value.
DEFAULT_DOWN_PAYMENT_PCT = Decimal("50")
DEFAULT_ON_IMPLEMENTATION_PCT = Decimal("50")
DEFAULT_MAINTENANCE_PCT = Decimal("30")


def _pct_env(name: str, default: Decimal) -> Decimal:
    raw = os.getenv(name, "").strip()
    if raw:
        try:
            value = Decimal(raw)
            if Decimal("0") <= value <= Decimal("100"):
                return value
        except InvalidOperation:
            pass
    return default


def down_payment_pct() -> Decimal:
    return _pct_env("QUOTE_DOWN_PAYMENT_PCT", DEFAULT_DOWN_PAYMENT_PCT)


def on_implementation_pct() -> Decimal:
    return _pct_env("QUOTE_ON_IMPLEMENTATION_PCT", DEFAULT_ON_IMPLEMENTATION_PCT)


def maintenance_pct() -> Decimal:
    return _pct_env("QUOTE_MAINTENANCE_PCT", DEFAULT_MAINTENANCE_PCT)


def _q(value: Decimal | float | int | str) -> Decimal:
    return Decimal(str(value)).quantize(CENTS, rounding=ROUND_HALF_UP)


def vat_rate() -> Decimal:
    raw = os.getenv("QUOTE_VAT_RATE", "").strip()
    if raw:
        try:
            value = Decimal(raw)
            if Decimal("0") <= value < Decimal("1"):
                return value
        except InvalidOperation:
            pass
    return DEFAULT_VAT_RATE


def validity_days() -> int:
    try:
        return max(1, int(os.getenv("QUOTE_VALIDITY_DAYS", str(DEFAULT_VALIDITY_DAYS))))
    except ValueError:
        return DEFAULT_VALIDITY_DAYS


def quote_number(prefix: str = "QT") -> str:
    """Human-quotable reference, e.g. ``QT-20261005-4F2A``."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"{prefix}-{stamp}-{secrets.token_hex(2).upper()}"


def product_cost_ratio(product: dict[str, Any]) -> Decimal:
    """Share of revenue consumed by hosting/support (i.e. COGS ratio)."""
    raw = product.get("cost_ratio")
    try:
        if raw is not None:
            value = Decimal(str(raw))
            if Decimal("0") <= value < Decimal("1"):
                return value
    except Exception:  # noqa: BLE001 - fall back to a sane default
        pass
    return Decimal("0.28")


@dataclass
class LineItem:
    description: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "detail": self.detail,
            "quantity": float(self.quantity),
            "unit_price": float(self.unit_price),
            "amount": float(self.amount),
        }


@dataclass
class Quotation:
    reference: str
    product: dict[str, Any]
    customer: dict[str, Any]
    currency: str
    lines: list[LineItem] = field(default_factory=list)
    subtotal: Decimal = Decimal("0.00")
    discount_pct: Decimal = Decimal("0.00")
    discount_amount: Decimal = Decimal("0.00")
    net: Decimal = Decimal("0.00")
    vat: Decimal = Decimal("0.00")
    total: Decimal = Decimal("0.00")
    vat_rate: Decimal = DEFAULT_VAT_RATE
    vat_inclusive: bool = True
    seats: int = 1
    term_months: int = 12
    valid_until: str = ""
    created_at: str = ""
    maintenance: Decimal = Decimal("0.00")
    maintenance_rate: Decimal = DEFAULT_MAINTENANCE_PCT
    year_one_total: Decimal = Decimal("0.00")
    payment_schedule: list[dict[str, Any]] = field(default_factory=list)

    @property
    def contract_value(self) -> Decimal:
        """Everything in the contract proper, excluding the maintenance retainer."""
        return self.net

    @property
    def monthly_equivalent(self) -> Decimal:
        if self.term_months <= 0:
            return self.net
        return _q(self.net / Decimal(self.term_months))

    def as_dict(self) -> dict[str, Any]:
        return {
            "reference": self.reference,
            "product": {
                "slug": self.product.get("slug"),
                "name": self.product.get("name"),
                "tagline": self.product.get("tagline"),
            },
            "customer": self.customer,
            "currency": self.currency,
            "seats": self.seats,
            "term_months": self.term_months,
            "lines": [line.as_dict() for line in self.lines],
            "subtotal": float(self.subtotal),
            "discount_pct": float(self.discount_pct),
            "discount_amount": float(self.discount_amount),
            "net": float(self.net),
            "vat": float(self.vat),
            "vat_rate": float(self.vat_rate),
            "vat_inclusive": self.vat_inclusive,
            "total": float(self.total),
            "monthly_equivalent": float(self.monthly_equivalent),
            "contract_value": float(self.contract_value),
            "maintenance": float(self.maintenance),
            "maintenance_rate": float(self.maintenance_rate),
            "year_one_total": float(self.year_one_total),
            "payment_schedule": self.payment_schedule,
            "valid_until": self.valid_until,
            "created_at": self.created_at,
        }


def build_quotation(
    product: dict[str, Any],
    customer: dict[str, Any],
    seats: int = 1,
    term_months: int = 12,
    discount_pct: float = 0.0,
    support: bool = False,
) -> Quotation:
    """Build a quotation for one product.

    Args:
        product: a catalog entry.
        customer: ``{name, email, organisation, phone}``.
        seats: number of users being licensed.
        term_months: contract length in months.
        discount_pct: 0-100, applied to the whole quote.
        support: add the optional annual support line.

    Raises:
        ValueError: on out-of-range seats, term or discount.
    """
    seats = max(1, int(seats or 1))
    term_months = max(1, int(term_months or 12))

    discount = Decimal(str(discount_pct or 0))
    if discount < 0 or discount > Decimal("100"):
        raise ValueError("discount_pct must be between 0 and 100")
    if discount != Decimal("0"):
        discount = discount.quantize(Decimal("0.01"))

    code = currency.base_currency()
    monthly = _q(product["price_month"])
    setup = _q(product["price_setup"])

    lines: list[LineItem] = []

    subscription = _q(monthly * Decimal(seats) * Decimal(term_months))
    lines.append(
        LineItem(
            description=f"{product['name']} subscription",
            detail=f"{seats} seat{'s' if seats != 1 else ''} × {term_months} months",
            quantity=Decimal(seats) * Decimal(term_months),
            unit_price=monthly,
            amount=subscription,
        )
    )

    if setup > 0:
        lines.append(
            LineItem(
                description="Implementation and onboarding",
                detail="One-off: data import, configuration and staff training",
                quantity=Decimal(1),
                unit_price=setup,
                amount=setup,
            )
        )

    if support:
        support_amount = _q(subscription * SUPPORT_RATE)
        lines.append(
            LineItem(
                description="Annual support and updates",
                detail="Priority support, upgrades and security patches",
                quantity=Decimal(1),
                unit_price=support_amount,
                amount=support_amount,
            )
        )

    subtotal = _q(sum((line.amount for line in lines), Decimal("0.00")))
    discount_amount = _q(subtotal * discount / Decimal("100"))
    net = _q(subtotal - discount_amount)

    # Catalog prices are VAT-inclusive, so VAT is extracted from the net amount
    # rather than added on top.
    rate = vat_rate()
    if rate > 0:
        vat = _q(net - (net / (Decimal("1") + rate)))
    else:
        vat = Decimal("0.00")

    now = datetime.now(timezone.utc)
    quotation = Quotation(
        reference=quote_number(),
        product=product,
        customer={
            "name": (customer.get("name") or "").strip() or "there",
            "email": (customer.get("email") or "").strip(),
            "organisation": (customer.get("organisation") or "").strip(),
            "phone": (customer.get("phone") or "").strip(),
        },
        currency=code,
        lines=lines,
        subtotal=subtotal,
        discount_pct=discount,
        discount_amount=discount_amount,
        net=net,
        vat=vat,
        total=net,
        vat_rate=rate,
        vat_inclusive=True,
        seats=seats,
        term_months=term_months,
        valid_until=(now.date() + timedelta(days=validity_days())).isoformat(),
        created_at=now.isoformat(timespec="seconds"),
    )

    # Annual maintenance retainer, charged on the contract value.
    rate_m = maintenance_pct()
    quotation.maintenance_rate = rate_m
    quotation.maintenance = _q(net * rate_m / Decimal("100"))
    quotation.year_one_total = _q(net + quotation.maintenance)

    # 50% on approval, 50% on implementation completion, maintenance invoiced
    # annually from go-live. Offline/on-premise deployment.
    down_pct = down_payment_pct()
    impl_pct = on_implementation_pct()
    down_amount = _q(net * down_pct / Decimal("100"))
    impl_amount = _q(net - down_amount)
    quotation.payment_schedule = [
        {
            "label": "50% down payment — on approval of this quotation",
            "trigger": "On approval",
            "percent": float(down_pct),
            "amount": float(down_amount),
        },
        {
            "label": "50% balance — on completion of implementation",
            "trigger": "On go-live",
            "percent": float(impl_pct),
            "amount": float(impl_amount),
        },
        {
            "label": f"Annual maintenance retainer ({pct(rate_m)}% of contract value, billed yearly)",
            "trigger": "Annually from go-live",
            "percent": float(rate_m),
            "amount": float(quotation.maintenance),
        },
    ]
    return quotation


def gross_margin(quotation: Quotation, product: dict[str, Any]) -> Decimal:
    """Gross margin the Accounting AI checks a quote against.

    Measured on the first-year revenue (contract + annual maintenance), since
    that is what the business actually books in year one.
    """
    revenue = quotation.year_one_total
    if revenue <= 0:
        return Decimal("0")
    cost = _q(revenue * product_cost_ratio(product))
    return _q((revenue - cost) / revenue * Decimal("100"))


def money(amount: float | Decimal, code: str | None = None) -> str:
    return currency.format_money(float(amount), code)


def pct(value: Decimal | float | int) -> str:
    """Format a percentage without scientific notation.

    ``Decimal("30").normalize()`` yields ``3E+1``, which must never reach a
    customer-facing quote.
    """
    try:
        return format(Decimal(str(value)).normalize(), "f")
    except (InvalidOperation, TypeError, ValueError):
        return str(value)


def render_text(quotation: Quotation, note: str = "") -> str:
    """Plain-text quotation for the e-mail body."""
    code = quotation.currency
    lines: list[str] = []
    lines.append(f"QUOTATION {quotation.reference}")
    lines.append(quotation.product["name"])
    lines.append("")
    lines.append(f"To      : {quotation.customer['name']}")
    if quotation.customer["organisation"]:
        lines.append(f"Company : {quotation.customer['organisation']}")
    lines.append(f"Date    : {quotation.created_at[:10]}")
    lines.append(f"Valid   : until {quotation.valid_until}")
    lines.append("")
    lines.append("ITEMS")
    for line in quotation.lines:
        lines.append(f"  - {line.description}")
        if line.detail:
            lines.append(f"      {line.detail}")
        lines.append(f"      {money(line.amount, code)}")
    lines.append("")
    lines.append(f"Subtotal        {money(quotation.subtotal, code)}")
    if quotation.discount_amount > 0:
        lines.append(
            f"Discount ({pct(quotation.discount_pct)}%)  -{money(quotation.discount_amount, code)}"
        )
    lines.append(f"Net (VAT incl.)  {money(quotation.net, code)}")
    lines.append(
        f"Of which VAT     {money(quotation.vat, code)} @ {pct(quotation.vat_rate * 100)}%"
    )
    lines.append(f"TOTAL           {money(quotation.total, code)}")
    lines.append(
        f"Monthly equiv.  {money(quotation.monthly_equivalent, code)} over {quotation.term_months} months"
    )
    lines.append("")
    lines.append("PAYMENT TERMS")
    for item in quotation.payment_schedule:
        lines.append(f"  {item['label']}")
        lines.append(f"      Due: {item['trigger']} — {money(item['amount'], code)}")
    lines.append(
        f"  First-year total: {money(quotation.year_one_total, code)} "
        f"(contract {money(quotation.contract_value, code)} + maintenance "
        f"{money(quotation.maintenance, code)})"
    )
    lines.append("")
    if note:
        lines.append(note)
        lines.append("")
    lines.append("Prices are in Philippine peso and are VAT-inclusive.")
    lines.append("This quotation is valid until the date shown above.")
    return "\n".join(lines)


def render_html(quotation: Quotation, note: str = "") -> str:
    """Minimal HTML alternative for clients that prefer rich mail."""
    code = quotation.currency
    rows = "\n".join(
        f"      <tr><td>{line.description}"
        + (f"<br><small>{line.detail}</small>" if line.detail else "")
        + f"</td><td style='text-align:right'>{money(line.amount, code)}</td></tr>"
        for line in quotation.lines
    )
    discount_row = (
        f"      <tr><td>Discount ({pct(quotation.discount_pct)}%)</td>"
        f"<td style='text-align:right'>-{money(quotation.discount_amount, code)}</td></tr>"
        if quotation.discount_amount > 0
        else ""
    )
    schedule = "\n".join(
        f"    <tr><td>{item['label']}<br><small>Due: {item['trigger']}</small></td>"
        f"<td style='text-align:right'>{money(item['amount'], code)}</td></tr>"
        for item in quotation.payment_schedule
    )
    return f"""<div style="font-family:system-ui,sans-serif;color:#0f172a">
  <h2>Quotation {quotation.reference}</h2>
  <p><strong>{quotation.product['name']}</strong><br>{quotation.product['tagline']}</p>
  <table cellpadding="6" style="border-collapse:collapse;width:100%">
    {rows}
    <tr><td colspan="2"><hr></td></tr>
    <tr><td>Subtotal</td><td style="text-align:right">{money(quotation.subtotal, code)}</td></tr>
    {discount_row}
    <tr><td><strong>Contract value</strong> (VAT inclusive)</td><td style="text-align:right"><strong>{money(quotation.contract_value, code)}</strong></td></tr>
    <tr><td>Of which VAT @ {pct(quotation.vat_rate * 100)}%</td><td style="text-align:right">{money(quotation.vat, code)}</td></tr>
  </table>
  <h3>Payment terms</h3>
  <table cellpadding="6" style="border-collapse:collapse;width:100%">
    {schedule}
    <tr><td><strong>First-year total</strong></td><td style="text-align:right"><strong>{money(quotation.year_one_total, code)}</strong></td></tr>
  </table>
  <p><small>Valid until {quotation.valid_until}. Monthly equivalent {money(quotation.monthly_equivalent, code)}.</small></p>
  {f"<p>{note}</p>" if note else ""}
</div>"""