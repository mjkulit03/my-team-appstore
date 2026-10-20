"""Accounting Agent (simulated).

Input:  raw income/expense entries.
Output: a summarised financial status report.

Money is handled with :class:`decimal.Decimal` and quantised to cents, so
totals never drift the way float arithmetic does (0.1 + 0.2 style bugs).
Floats only appear at the JSON boundary.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date as date_cls
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from . import textkit as tk

CENTS = Decimal("0.01")
VALID_TYPES = ("income", "expense")

# An expense line above this share of all spending earns a concentration warning.
CONCENTRATION_THRESHOLD = Decimal("0.40")
# Profit margin below this earns a thin-margin warning.
THIN_MARGIN_THRESHOLD = Decimal("0.10")


def _to_money(value) -> Decimal:
    """Coerce input to a cent-quantised Decimal, rejecting nonsense early."""
    if isinstance(value, Decimal):
        dec = value
    elif isinstance(value, bool) or value is None:
        raise ValueError("amount must be a number, not a boolean or null")
    elif isinstance(value, (int, float, str)):
        try:
            dec = Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise ValueError(f"amount {value!r} is not a valid number") from None
    else:
        raise ValueError(f"amount must be a number, got {type(value).__name__}")

    if not dec.is_finite():
        raise ValueError(f"amount {value!r} is not a finite number")

    dec = dec.quantize(CENTS, rounding=ROUND_HALF_UP)
    if dec <= 0:
        raise ValueError("amount must be greater than zero; use type='expense' to record spending")
    return dec


def _to_signed_money(value) -> Decimal:
    """Like :func:`_to_money` but allows negative values (opening balance)."""
    if isinstance(value, bool) or value is None:
        raise ValueError("opening_balance must be a number, not a boolean or null")
    try:
        dec = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"opening_balance {value!r} is not a valid number") from None
    if not dec.is_finite():
        raise ValueError(f"opening_balance {value!r} is not a finite number")
    return dec.quantize(CENTS, rounding=ROUND_HALF_UP)


def _out(dec: Decimal) -> float:
    """Decimal -> float for JSON, keeping exactly two decimal places."""
    return float(dec.quantize(CENTS, rounding=ROUND_HALF_UP))


def _alert(level: str, code: str, message: str) -> dict:
    return {"level": level, "code": code, "message": message}


def _build_alerts(
    total_income: Decimal,
    total_expenses: Decimal,
    net: Decimal,
    margin: Decimal | None,
    expense_shares: dict[str, Decimal],
    entry_count: int,
    opening_balance: Decimal,
) -> list[dict]:
    alerts: list[dict] = []

    if entry_count == 0:
        alerts.append(_alert("info", "no_data", "No entries supplied, so this report describes an empty ledger."))

    if total_income == 0 and total_expenses > 0:
        alerts.append(_alert("critical", "no_income", "Spending was recorded but no income at all. Check the ledger is complete."))
    elif total_expenses == 0 and total_income > 0:
        alerts.append(_alert("info", "no_expenses", "Income recorded with no expenses. This is almost always a missing-data problem."))

    if net < 0:
        alerts.append(
            _alert(
                "critical",
                "net_loss",
                f"Net loss of {tk.money(_out(-net))}. Expenses exceed income by the same amount.",
            )
        )
    elif net == 0:
        alerts.append(_alert("warning", "break_even", "Exactly break-even: no buffer for an unexpected cost."))

    if margin is not None and margin < 0:
        pass  # already reported as net_loss; don't double-alert
    elif margin is not None and margin < THIN_MARGIN_THRESHOLD:
        alerts.append(
            _alert(
                "warning",
                "thin_margin",
                f"Profit margin is {margin * 100:.1f}%, under the {THIN_MARGIN_THRESHOLD * 100:.0f}% thin-margin threshold.",
            )
        )

    for category, share in expense_shares.items():
        if share > CONCENTRATION_THRESHOLD:
            alerts.append(
                _alert(
                    "warning",
                    "expense_concentration",
                    f"'{category}' is {share * 100:,.2f}% of all spending, above the {CONCENTRATION_THRESHOLD * 100:.0f}% concentration threshold.",
                )
            )

    if opening_balance < 0:
        alerts.append(_alert("critical", "negative_opening_balance", f"Opening balance is negative ({tk.money(_out(opening_balance))})."))

    if not alerts:
        alerts.append(_alert("ok", "healthy", "No issues detected in the supplied entries."))

    order = {"critical": 0, "warning": 1, "info": 2, "ok": 3}
    return sorted(alerts, key=lambda a: order[a["level"]])





def run_accounting_agent(
    entries: list[dict],
    opening_balance: float = 0.0,
    currency: str = "USD",
    top_n: int = 5,
) -> dict:
    """Summarise raw income and expense entries into a financial status report.

    Args:
        entries: List of ``{"type": "income"|"expense", "amount": number,
            "category": str, "description": str, "date": "YYYY-MM-DD" (optional)}``.
        opening_balance: Cash on hand at period start.
        currency: ISO code, recorded in the output.
        top_n: How many largest expenses to list individually.

    Returns:
        A JSON-serialisable dict with totals, category breakdowns, monthly
        totals, largest expenses and alerts.

    Raises:
        ValueError: on empty input, malformed entries, or non-positive amounts.
    """
    if not isinstance(entries, list):
        raise ValueError("entries must be a list")
    if not entries:
        raise ValueError("entries is required and cannot be empty")

    opening = _to_signed_money(opening_balance)
    if top_n < 1:
        raise ValueError("top_n must be at least 1")

    income_by_category: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    expense_by_category: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    monthly: dict[str, dict[str, Decimal]] = defaultdict(lambda: {"income": Decimal("0.00"), "expense": Decimal("0.00")})
    expenses_list: list[dict] = []
    dated_count = 0
    total_income = Decimal("0.00")
    total_expenses = Decimal("0.00")

    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"entry #{index + 1} must be an object, got {type(entry).__name__}")

        entry_type = str(entry.get("type", "")).strip().lower()
        if entry_type not in VALID_TYPES:
            raise ValueError(f"entry #{index + 1}: type must be one of {', '.join(VALID_TYPES)} (got {entry.get('type')!r})")

        category = str(entry.get("category", "")).strip()
        if not category:
            raise ValueError(f"entry #{index + 1}: category is required")
        category = category.title()

        amount = _to_money(entry.get("amount"))

        raw_date = entry.get("date")
        parsed_date = None
        if raw_date:
            if isinstance(raw_date, str):
                try:
                    parsed_date = date_cls.fromisoformat(raw_date.strip())
                except ValueError:
                    raise ValueError(f"entry #{index + 1}: date must be ISO YYYY-MM-DD (got {raw_date!r})") from None
            elif isinstance(raw_date, date_cls):
                parsed_date = raw_date
            else:
                raise ValueError(f"entry #{index + 1}: date must be a YYYY-MM-DD string")
            dated_count += 1

        description = str(entry.get("description", "")).strip()

        if entry_type == "income":
            total_income += amount
            income_by_category[category] += amount
        else:
            total_expenses += amount
            expense_by_category[category] += amount
            expenses_list.append(
                {
                    "date": parsed_date.isoformat() if parsed_date else None,
                    "category": category,
                    "description": description,
                    "amount": _out(amount),
                }
            )

        if parsed_date:
            bucket = monthly[parsed_date.strftime("%Y-%m")]
            bucket[entry_type] += amount

    net = total_income - total_expenses
    closing = opening + net
    margin = (net / total_income) if total_income > 0 else None

    expense_shares = {
        category: (value / total_expenses) for category, value in expense_by_category.items()
    } if total_expenses > 0 else {}

    top_expenses = sorted(expenses_list, key=lambda e: (-e["amount"], e["category"]))[:top_n]

    monthly_totals = None
    if dated_count == len(entries):
        monthly_totals = {
            month: {
                "income": _out(values["income"]),
                "expenses": _out(values["expense"]),
                "net": _out(values["income"] - values["expense"]),
            }
            for month, values in sorted(monthly.items())
        }

    alerts = _build_alerts(total_income, total_expenses, net, margin, expense_shares, len(entries), opening)
    level_counts: dict[str, int] = defaultdict(int)
    for alert in alerts:
        level_counts[alert["level"]] += 1

    status = "critical" if level_counts["critical"] else ("needs_attention" if level_counts["warning"] else "healthy")

    return {
        "agent": "accounting",
        "currency": currency.upper(),
        "status": status,
        "entry_count": len(entries),
        "dated_entry_count": dated_count,
        "totals": {
            "opening_balance": _out(opening),
            "total_income": _out(total_income),
            "total_expenses": _out(total_expenses),
            "net": _out(net),
            "closing_balance": _out(closing),
            "profit_margin_pct": round(float(margin * 100), 2) if margin is not None else None,
            "expense_ratio_pct": round(float((total_expenses / total_income) * 100), 2) if total_income > 0 else None,
        },
        "income_by_category": [
            {"category": c, "amount": _out(v), "share_pct": round(float((v / total_income) * 100), 2)}
            for c, v in sorted(income_by_category.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        "expenses_by_category": [
            {
                "category": c,
                "amount": _out(v),
                "share_pct": round(float((v / total_expenses) * 100), 2),
            }
            for c, v in sorted(expense_by_category.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        "monthly_totals": monthly_totals,
        "top_expenses": top_expenses,
        "alerts": alerts,
        "generated_by": "simulated-rules-engine",
    }