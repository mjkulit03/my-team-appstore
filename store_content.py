"""Editable storefront content: prices, product labels and page copy.

``docs/store-content.json`` is the one file the browser-based admin editor
writes. GitHub Pages serves it as static data and ``tools/build_store.py`` reads
it at build time, so the published page cannot drift from the file.

Division of responsibility:

- ``catalog/products.py`` stays the source of truth for *which* products exist,
  and for their descriptions, features and icons.
- This module owns only what an admin is allowed to change: each product's name,
  tagline, category, monthly price and setup fee, plus the page copy around them.

Anything missing, malformed or out of range falls back to the catalog value, so a
half-edited file can never break the build or publish a nonsense price.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import catalog

CONTENT_PATH = Path(__file__).resolve().parent / "docs" / "store-content.json"
CONTENT_VERSION = 1

#: Longest a single free-text field may be, to keep the layout intact.
MAX_TEXT = {"name": 80, "tagline": 220, "category": 48}
MAX_COPY = 1200
#: Sanity ceiling for a price. Guards against a stray extra zero.
MAX_PRICE = 10_000_000

#: Text the admin can rewrite. ``{count}`` is replaced with the product count.
PAGE_COPY_DEFAULTS: dict[str, str] = {
    "brand_tagline": "Business systems, ready to deploy",
    "hero_eyebrow": "{count} systems · one store",
    "hero_headline": "Software your business can run on day one.",
    "hero_lede": (
        "Inventory, assets, HR, projects, retail, attendance, records and security "
        "awareness — built for Philippine organisations, delivered on-premise or "
        "offline, and priced in pesos with no per-user surprises."
    ),
    "catalog_heading": "The catalog",
    "catalog_description": (
        "Every system is sold on its own, or run several on one shared record of "
        "your stock, staff and documents."
    ),
    "bundle_heading": "Run the whole suite.",
    "bundle_body": (
        "One contract for all {count} systems, one deployment, one support line. "
        "Shared staff and asset records mean the systems stop contradicting each "
        "other, and every new system you add later plugs into the same foundation."
    ),
    "footer_line": (
        "{count} business systems. Prices in Philippine peso (PHP), VAT inclusive."
    ),
}

PRICE_KEYS = ("price_month", "price_setup")
LABEL_KEYS = ("name", "tagline", "category")

#: Human labels for the copy fields, in the order the editor shows them.
COPY_LABELS: dict[str, str] = {
    "hero_headline": "Hero headline",
    "hero_eyebrow": "Hero eyebrow",
    "hero_lede": "Hero paragraph",
    "catalog_heading": "Catalog heading",
    "catalog_description": "Catalog description",
    "bundle_heading": "Bundle heading",
    "bundle_body": "Bundle paragraph",
    "brand_tagline": "Logo tagline",
    "footer_line": "Footer line",
}


class ContentError(ValueError):
    """Raised when a content document cannot be parsed at all."""


# --------------------------------------------------------------- helpers


def _clean_text(value: Any, limit: int) -> str | None:
    """Trimmed string within ``limit``, or None when unusable."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or len(text) > limit:
        return None
    return text


def _clean_price(value: Any) -> int | None:
    """Non-negative whole peso amount, or None when unusable.

    Accepts ``1490``, ``"1,490"``, ``"₱1490"`` and ``1490.0`` — the admin editor
    sends numbers, but the file is also hand-editable.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "").replace("₱", "").replace("PHP", "").strip()
        if not cleaned:
            return None
        try:
            value = float(cleaned)
        except ValueError:
            return None
    if not isinstance(value, (int, float)):
        return None
    if value != value or value in (float("inf"), float("-inf")):
        return None
    if value < 0 or value > MAX_PRICE:
        return None
    return int(round(value))


def _empty_document() -> dict[str, Any]:
    return {"version": CONTENT_VERSION, "prices": {}, "labels": {}, "copy": {}}


# --------------------------------------------------------------- parsing


def normalize(data: Any) -> dict[str, Any]:
    """Validate a document, dropping anything invalid.

    Unknown slugs and unknown copy keys are discarded; invalid values are
    dropped so the catalog default shows through. Never raises for content
    problems — a bad file degrades to the catalog, it does not break the site.
    """
    document = _empty_document()
    if not isinstance(data, dict):
        return document

    known_slugs = {p["slug"] for p in catalog.list_products()}
    copy_keys = set(PAGE_COPY_DEFAULTS)

    prices = data.get("prices")
    if isinstance(prices, dict):
        for slug, fields in prices.items():
            if slug not in known_slugs or not isinstance(fields, dict):
                continue
            clean = {}
            for key in PRICE_KEYS:
                amount = _clean_price(fields.get(key))
                if amount is not None:
                    clean[key] = amount
            if clean:
                document["prices"][slug] = clean

    labels = data.get("labels")
    if isinstance(labels, dict):
        for slug, fields in labels.items():
            if slug not in known_slugs or not isinstance(fields, dict):
                continue
            clean = {}
            for key in LABEL_KEYS:
                text = _clean_text(fields.get(key), MAX_TEXT[key])
                if text is not None:
                    clean[key] = text
            if clean:
                document["labels"][slug] = clean

    copy = data.get("copy")
    if isinstance(copy, dict):
        for key, value in copy.items():
            if key not in copy_keys:
                continue
            text = _clean_text(value, MAX_COPY)
            if text is not None:
                document["copy"][key] = text

    updated = data.get("updated_at")
    if isinstance(updated, str) and len(updated) <= 40:
        document["updated_at"] = updated.strip()
    return document


def validate(data: Any) -> list[str]:
    """Explain what is wrong with a document, so an editor can refuse it.

    ``normalize`` silently drops bad values (right for a hand-edited file that
    must not break the build). An interactive editor is different: it should say
    what is wrong instead of appearing to save a value that then disappears.
    Returns an empty list when the document is usable.
    """
    if not isinstance(data, dict):
        return ["The content document must be a JSON object."]

    problems: list[str] = []
    known_slugs = {p["slug"] for p in catalog.list_products()}

    prices = data.get("prices")
    if prices is not None and not isinstance(prices, dict):
        problems.append("`prices` must be an object keyed by product slug.")
    elif isinstance(prices, dict):
        for slug, fields in prices.items():
            if slug not in known_slugs:
                problems.append(f"Unknown product {slug!r} in `prices`.")
                continue
            if not isinstance(fields, dict):
                problems.append(f"Prices for {slug!r} must be an object.")
                continue
            for key in PRICE_KEYS:
                if key not in fields:
                    continue
                if _clean_price(fields[key]) is None:
                    label = "monthly price" if key == "price_month" else "setup fee"
                    problems.append(
                        f"{slug}: the {label} must be a whole peso amount between 0 and {MAX_PRICE:,}."
                    )

    labels = data.get("labels")
    if labels is not None and not isinstance(labels, dict):
        problems.append("`labels` must be an object keyed by product slug.")
    elif isinstance(labels, dict):
        for slug, fields in labels.items():
            if slug not in known_slugs:
                problems.append(f"Unknown product {slug!r} in `labels`.")
                continue
            if not isinstance(fields, dict):
                problems.append(f"Labels for {slug!r} must be an object.")
                continue
            for key in LABEL_KEYS:
                if key not in fields:
                    continue
                if _clean_text(fields[key], MAX_TEXT[key]) is None:
                    problems.append(
                        f"{slug}: the {key} must be text of 1-{MAX_TEXT[key]} characters."
                    )

    copy = data.get("copy")
    if copy is not None and not isinstance(copy, dict):
        problems.append("`copy` must be an object of page-copy fields.")
    elif isinstance(copy, dict):
        for key, value in copy.items():
            if key not in PAGE_COPY_DEFAULTS:
                problems.append(f"Unknown page-copy field {key!r}.")
                continue
            if _clean_text(value, MAX_COPY) is None:
                problems.append(f"{COPY_LABELS.get(key, key)} must be text of 1-{MAX_COPY} characters.")

    return problems


def load(path: Path | None = None) -> dict[str, Any]:
    """Read and validate the content file. Missing file means "all defaults"."""
    target = Path(path) if path else CONTENT_PATH
    try:
        raw = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return _empty_document()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ContentError(f"{target.name} is not valid JSON: {exc}") from exc
    return normalize(data)


def dumps(document: dict[str, Any]) -> str:
    """Serialise for the admin editor: stable order, readable diffs."""
    clean = normalize(document)
    return json.dumps(clean, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def save(document: dict[str, Any], path: Path | None = None) -> Path:
    """Write a validated document. Used by the CLI and by tests."""
    target = Path(path) if path else CONTENT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(dumps(document), encoding="utf-8")
    return target


# --------------------------------------------------------------- applying


def apply(products: list[dict[str, Any]], document: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the catalog with the admin's overrides layered on top."""
    prices = document.get("prices") or {}
    labels = document.get("labels") or {}
    merged: list[dict[str, Any]] = []
    for product in products:
        item = dict(product)
        item.update(labels.get(product["slug"]) or {})
        item.update(prices.get(product["slug"]) or {})
        merged.append(item)
    return merged


def page_copy(document: dict[str, Any], count: int | None = None) -> dict[str, str]:
    """Page copy with ``{count}`` substituted. ``count`` defaults to the catalog size."""
    if count is None:
        count = len(catalog.list_products())
    copy = document.get("copy") or {}
    resolved = {}
    for key, default in PAGE_COPY_DEFAULTS.items():
        text = copy.get(key) or default
        resolved[key] = text.replace("{count}", str(count))
    # Tab titles and meta descriptions read better without the count placeholder
    # leaking through when an admin removes it.
    resolved["count"] = str(count)
    return resolved


def document_from_catalog() -> dict[str, Any]:
    """A ready-to-edit document seeded with the catalog's current values.

    Written once by ``python tools/build_store.py --init-content`` and then owned
    by the admin editor, so the file always lists every product explicitly.
    """
    prices = {}
    labels = {}
    for product in catalog.list_products():
        prices[product["slug"]] = {key: int(product[key]) for key in PRICE_KEYS}
        labels[product["slug"]] = {key: str(product[key]) for key in LABEL_KEYS}
    return {
        "version": CONTENT_VERSION,
        "prices": prices,
        "labels": labels,
        "copy": dict(PAGE_COPY_DEFAULTS),
    }
