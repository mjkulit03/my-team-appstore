"""Small JSON-file persistence for leads, escalations and campaign drafts.

Deliberately dependency-free so the project deploys for free. Suitable for a
single instance: state lives in one JSON file guarded by an in-process lock. For
multi-instance or high-volume use, swap this module for a real database.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _empty() -> dict[str, Any]:
    return {
        "leads": [], "escalations": [], "campaigns": [], "events": [], "users": [], "quotations": []
    }


def _store_path() -> Path:
    """Resolve the store file from the environment on every call.

    Read lazily (not at import time) so the location can be redirected in
    tests and changed at runtime without reimporting the module.
    """
    return Path(os.getenv("DATA_DIR", "var")) / "store.json"


def _read(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _empty()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _empty()
    base = _empty()
    if isinstance(data, dict):
        for key in base:
            if isinstance(data.get(key), list):
                base[key] = data[key]
    return base


def _write(path: Path, data: dict[str, Any]) -> None:
    """Atomic write so a crash mid-save cannot corrupt the file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _mutate(mutator: Callable[[dict[str, Any]], Any]) -> Any:
    path = _store_path()
    with _LOCK:
        data = _read(path)
        result = mutator(data)
        _write(path, data)
        return result


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


# ---------------------------------------------------------------- leads


def create_lead(**fields: Any) -> dict[str, Any]:
    """Record a storefront inquiry."""
    lead = {
        "id": _new_id("lead"),
        "created_at": _now(),
        "status": "new",
        **fields,
    }

    def apply(data: dict[str, Any]) -> dict[str, Any]:
        data["leads"].append(lead)
        return lead

    return _mutate(apply)


def list_leads() -> list[dict[str, Any]]:
    data = _read(_store_path())
    return list(reversed(data["leads"]))


def get_lead(lead_id: str) -> dict[str, Any] | None:
    for lead in _read(_store_path())["leads"]:
        if lead["id"] == lead_id:
            return lead
    return None


# ---------------------------------------------------------- escalations


def create_escalation(kind: str, severity: str, title: str, summary: str, **fields: Any) -> dict[str, Any]:
    """Queue something that needs a human decision."""
    escalation = {
        "id": _new_id("esc"),
        "kind": kind,
        "severity": severity,
        "title": title,
        "summary": summary,
        "status": "pending",
        "created_at": _now(),
        "resolved_at": None,
        "resolution_note": None,
        **fields,
    }

    def apply(data: dict[str, Any]) -> dict[str, Any]:
        data["escalations"].append(escalation)
        return escalation

    return _mutate(apply)


def list_escalations(status: str | None = None) -> list[dict[str, Any]]:
    items = _read(_store_path())["escalations"]
    if status:
        items = [e for e in items if e["status"] == status]
    return list(reversed(items))


def get_escalation(escalation_id: str) -> dict[str, Any] | None:
    for item in _read(_store_path())["escalations"]:
        if item["id"] == escalation_id:
            return item
    return None


def resolve_escalation(escalation_id: str, note: str, resolution: str = "approved") -> dict[str, Any] | None:
    def apply(data: dict[str, Any]) -> dict[str, Any] | None:
        for item in data["escalations"]:
            if item["id"] == escalation_id:
                item["status"] = "resolved"
                item["resolution"] = resolution
                item["resolution_note"] = note
                item["resolved_at"] = _now()
                return item
        return None

    return _mutate(apply)


def mark_notified(escalation_id: str, result: dict[str, Any]) -> None:
    """Record delivery outcome so the worker does not send the same alert twice."""

    def apply(data: dict[str, Any]) -> None:
        for item in data["escalations"]:
            if item["id"] == escalation_id:
                item["notified_at"] = _now()
                item["notification"] = result
                return

    _mutate(apply)


# --------------------------------------------------------------- events

# Keep the event log bounded so the JSON file cannot grow without limit.
MAX_EVENTS = 5000


def append_event(kind: str, path: str, product_slug: str | None = None, referrer: str = "") -> dict[str, Any]:
    """Record one storefront event for later traffic analysis."""
    event = {
        "id": _new_id("evt"),
        "kind": kind,
        "path": path,
        "product_slug": product_slug,
        "referrer": (referrer or "")[:300],
        "at": _now(),
    }

    def apply(data: dict[str, Any]) -> dict[str, Any]:
        events = data.setdefault("events", [])
        events.append(event)
        if len(events) > MAX_EVENTS:
            del events[: len(events) - MAX_EVENTS]
        return event

    return _mutate(apply)


def list_events(limit: int | None = None) -> list[dict[str, Any]]:
    events = _read(_store_path()).get("events", [])
    events = list(reversed(events))
    return events[:limit] if limit else events


# ------------------------------------------------------------ campaigns


def save_campaign(product_slug: str, campaign: dict[str, Any]) -> dict[str, Any]:
    record = {
        "id": _new_id("camp"),
        "product_slug": product_slug,
        "created_at": _now(),
        "campaign": campaign,
    }

    def apply(data: dict[str, Any]) -> dict[str, Any]:
        data["campaigns"].append(record)
        return record

    return _mutate(apply)


# ----------------------------------------------------------- quotations


def create_quotation(product_slug: str, product_name: str, **fields: Any) -> dict[str, Any]:
    record = {
        "id": _new_id("qtn"),
        "product_slug": product_slug,
        "product_name": product_name,
        "created_at": _now(),
        "status": "pending_email",
        "email_sent": False,
        "email_detail": None,
        "escalation_id": None,
        **fields,
    }

    def apply(data: dict[str, Any]) -> dict[str, Any]:
        data.setdefault("quotations", []).append(record)
        return record

    return _mutate(apply)


def list_quotations() -> list[dict[str, Any]]:
    return list(reversed(_read(_store_path()).get("quotations", [])))


def get_quotation(quotation_id: str) -> dict[str, Any] | None:
    for item in _read(_store_path()).get("quotations", []):
        if item["id"] == quotation_id:
            return item
    return None


def update_quotation(quotation_id: str, **fields: Any) -> dict[str, Any] | None:
    def apply(data: dict[str, Any]) -> dict[str, Any] | None:
        for item in data.get("quotations", []):
            if item["id"] == quotation_id:
                item.update(fields)
                return item
        return None

    return _mutate(apply)


def list_campaigns() -> list[dict[str, Any]]:
    return list(reversed(_read(_store_path())["campaigns"]))


def reset_for_tests() -> None:
    """Clear persisted state. Used by the test suite only."""
    _mutate(lambda data: data.clear() or data.update(_empty()))