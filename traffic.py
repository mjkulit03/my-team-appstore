"""Traffic analysis for the control panel.

Dependency-free: events are appended to the same JSON store the rest of the app
uses and aggregated on read. This is deliberately small-scale analytics (page
views, referrers, funnel counts), not a full web-analytics product.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

import store

VIEW = "pageview"
INQUIRY = "inquiry"


def _parse(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def normalise_referrer(referrer: str) -> str:
    """Reduce a referrer to something readable, e.g. 'google.com'.

    Strips the scheme and any path/query so the same source groups together.
    """
    if not referrer:
        return "direct"
    parsed = urlparse(referrer if "//" in referrer else f"//{referrer}")
    host = (parsed.netloc or parsed.path or "").strip().lower()
    if not host:
        return "direct"
    if host in {"localhost", "127.0.0.1"}:
        return "internal"
    # "www." is not a meaningful distinction for analytics: group it with the
    # bare domain so one source does not split into two buckets.
    if host.startswith("www."):
        host = host[4:]
    return host


def record_view(path: str, product_slug: str | None = None, referrer: str = "") -> None:
    """Record a storefront page view."""
    store.append_event(VIEW, path, product_slug, normalise_referrer(referrer))


def record_inquiry(path: str, product_slug: str) -> None:
    """Record a demo request, for the view -> inquiry funnel."""
    store.append_event(INQUIRY, path, product_slug, "direct")


def summary(days: int = 7) -> dict[str, Any]:
    """Aggregate recent storefront traffic.

    Returns view counts, per-product interest, referrer sources, a daily series
    and a view -> inquiry conversion figure.
    """
    events = store.list_events()
    views = [e for e in events if e["kind"] == VIEW]
    inquiries = [e for e in events if e["kind"] == INQUIRY]

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    recent = [e for e in views if (_parse(e["at"]) or cutoff) >= cutoff]

    by_product: Counter[str] = Counter()
    for event in views:
        if event.get("product_slug"):
            by_product[event["product_slug"]] += 1

    by_referrer: Counter[str] = Counter(e.get("referrer") or "direct" for e in views)

    series: dict[str, int] = {}
    for offset in range(days - 1, -1, -1):
        day = (datetime.now(timezone.utc) - timedelta(days=offset)).date().isoformat()
        series[day] = 0
    for event in recent:
        stamp = _parse(event["at"])
        if stamp:
            key = stamp.date().isoformat()
            if key in series:
                series[key] += 1

    recent_inquiries = len([e for e in inquiries if (_parse(e["at"]) or cutoff) >= cutoff])
    conversion = round((len(inquiries) / len(views) * 100), 2) if views else 0.0

    return {
        "window_days": days,
        "total_views": len(views),
        "views_last_window": len(recent),
        "total_inquiries": len(inquiries),
        "inquiries_last_window": recent_inquiries,
        "conversion_pct": conversion,
        "views_by_product": dict(by_product.most_common()),
        "top_referrers": dict(by_referrer.most_common(8)),
        "daily_views": series,
        "most_viewed_products": [slug for slug, _ in by_product.most_common(3)],
    }