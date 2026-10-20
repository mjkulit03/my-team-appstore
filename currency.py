"""Currency handling, defaulting to Philippine peso (PHP).

The suite is priced in PHP because that is where it is sold. Other currencies are
supported for display and for the Accounting agent, converted at configurable rates.

Rates are indicative and deliberately static: this keeps the platform deterministic
and free (no FX API call per request). Override any rate with an environment
variable, e.g. ``FX_USD=0.0165`` meaning 1 PHP = 0.0165 USD.
"""

from __future__ import annotations

import os

BASE_CURRENCY = "PHP"

# Indicative units of each currency per 1 PHP. Display-only; see module docstring.
DEFAULT_RATES: dict[str, float] = {
    "PHP": 1.0,
    "USD": 0.0165,
    "EUR": 0.0152,
    "GBP": 0.0130,
    "JPY": 2.55,
    "SGD": 0.0222,
    "HKD": 0.1290,
    "AUD": 0.0252,
    "CAD": 0.0226,
    "AED": 0.0606,
}

SYMBOLS: dict[str, str] = {
    "PHP": "₱",
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
    "SGD": "S$",
    "HKD": "HK$",
    "AUD": "A$",
    "CAD": "C$",
    "AED": "AED",
}

SUPPORTED = tuple(DEFAULT_RATES)


def base_currency() -> str:
    """The currency the platform prices and reports in."""
    raw = (os.getenv("BASE_CURRENCY") or BASE_CURRENCY).strip().upper()
    return raw if raw in DEFAULT_RATES else BASE_CURRENCY


def rate(currency: str) -> float:
    """Units of ``currency`` per 1 PHP.

    ``FX_<CODE>`` in the environment overrides the default (e.g. FX_USD=0.0168).
    """
    code = (currency or "").strip().upper()
    override = os.getenv(f"FX_{code}")
    if override:
        try:
            value = float(override)
            if value > 0:
                return value
        except ValueError:
            pass
    return DEFAULT_RATES.get(code, 0.0)


def is_supported(currency: str) -> bool:
    return (currency or "").strip().upper() in DEFAULT_RATES


def convert(amount: float, from_currency: str, to_currency: str | None = None) -> float | None:
    """Convert between supported currencies. Returns None if either is unknown."""
    src = (from_currency or base_currency()).strip().upper()
    dst = (to_currency or base_currency()).strip().upper()
    if src not in DEFAULT_RATES or dst not in DEFAULT_RATES:
        return None
    # Convert to PHP first, then out to the target.
    in_php = amount / rate(src)
    return round(in_php * rate(dst), 2)


def symbol(currency: str | None = None) -> str:
    code = (currency or base_currency()).strip().upper()
    return SYMBOLS.get(code, code + " ")


def format_money(amount: float | None, currency: str | None = None, with_code: bool = False) -> str:
    """Render an amount with thousands separators, e.g. ``₱1,490.00``."""
    if amount is None:
        return "—"
    code = (currency or base_currency()).strip().upper()
    if code not in DEFAULT_RATES:
        return f"{code} {amount:,.2f}"
    text = f"{symbol(code)}{amount:,.2f}"
    return f"{text} {code}" if with_code else text


def format_dual(amount: float, currency: str | None = None) -> str:
    """Show the amount in the base currency with the USD equivalent underneath.

    Used on the storefront so customers always see peso, with an international
    figure when they need one.
    """
    code = (currency or base_currency()).strip().upper()
    primary = format_money(amount, code)
    if code == "USD" or "USD" not in DEFAULT_RATES:
        return primary
    usd = convert(amount, code, "USD")
    if usd is None:
        return primary
    return f"{primary} (~{format_money(usd, 'USD')})"


def catalog_price(amount_php: float) -> dict[str, object]:
    """Structured price for templates and JSON responses."""
    code = base_currency()
    usd = convert(amount_php, code, "USD")
    return {
        "amount": amount_php,
        "currency": code,
        "symbol": symbol(code),
        "formatted": format_money(amount_php, code),
        "formatted_dual": format_dual(amount_php, code),
        "usd_equivalent": usd,
    }