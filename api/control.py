"""Control-panel API. Every route requires an authenticated session.

- Reads: any signed-in role.
- Approve / reject / resolve, test notification, run worker: ``operator`` or ``admin``.
- User management: ``admin`` only.

Returns 503 (not 403) when the panel has no accounts configured, so operators can
tell "not set up" apart from "not permitted".
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

import auth
import currency
import store
import traffic
import users as users_module
from catalog import list_products
from notifications.config import get_settings
from notifications.worker import run_once

router = APIRouter(tags=["control"], dependencies=[Depends(auth.require_panel)])


class Resolution(BaseModel):
    note: str = Field(default="", max_length=1000)
    resolution: str = Field(default="approved", pattern="^(approved|rejected|deferred)$")


class TestNotification(BaseModel):
    subject: str = Field(default="Test alert from My Team", max_length=200)
    message: str = Field(default="Notifications are wired up correctly.", max_length=2000)


class NewUser(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=8, max_length=128)
    role: str = Field(default="analyst")
    display_name: str = Field(default="", max_length=80)


class UserUpdate(BaseModel):
    role: str | None = None
    display_name: str | None = Field(default=None, max_length=80)
    active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


@router.get("/api/control/overview")
def overview(request_user: users_module.User = Depends(auth.require_panel)) -> dict:
    """Everything the dashboard needs in one call."""
    settings = get_settings()
    escalations = store.list_escalations()
    leads = store.list_leads()
    code = currency.base_currency()
    return {
        "products": len(list_products()),
        "currency": code,
        "escalations": {
            "total": len(escalations),
            "pending": len([e for e in escalations if e["status"] == "pending"]),
            "by_kind": _count_by(escalations, "kind"),
        },
        "leads": {
            "total": len(leads),
            "by_product": _count_by(leads, "product_name"),
            "total_value": round(sum(float(l.get("estimated_value") or 0) for l in leads), 2),
        },
        "campaigns": len(store.list_campaigns()),
        "traffic": traffic.summary(),
        "notifications": settings.public_status(),
        "signed_in_as": request_user.public(),
    }


def _count_by(items: list[dict], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = item.get(key) or "unknown"
        counts[value] = counts.get(value, 0) + 1
    return counts


@router.get("/api/control/traffic")
def traffic_report(days: int = 7) -> dict:
    """Storefront traffic analysis for the AI workforce to act on."""
    if days < 1 or days > 90:
        raise HTTPException(status_code=400, detail="days must be between 1 and 90")
    return traffic.summary(days=days)


@router.get("/api/control/currency")
def currency_report() -> dict:
    """Base currency and the indicative conversion table in use."""
    code = currency.base_currency()
    return {
        "base_currency": code,
        "base_symbol": currency.symbol(code),
        "rates": {c: currency.rate(c) for c in currency.SUPPORTED},
        "usd_example": currency.format_dual(1000, code),
    }


@router.get("/api/control/escalations")
def escalations(status: str | None = None) -> dict:
    return {"escalations": store.list_escalations(status=status)}


@router.post("/api/control/escalations/{escalation_id}/resolve")
def resolve(
    escalation_id: str,
    resolution: Resolution,
    _: users_module.User = Depends(auth.require_role("admin", "operator")),
) -> dict:
    item = store.resolve_escalation(escalation_id, resolution.note, resolution.resolution)
    if item is None:
        raise HTTPException(status_code=404, detail=f"No escalation {escalation_id!r}")
    return item


@router.get("/api/control/leads")
def leads() -> dict:
    return {"leads": store.list_leads()}


@router.post("/api/control/notify/test")
def test_notification(
    payload: TestNotification,
    _: users_module.User = Depends(auth.require_role("admin", "operator")),
) -> dict:
    """Send a test alert through the configured channels."""
    from notifications.notifier import Notifier

    results = Notifier(get_settings()).send(payload.subject, payload.message)
    return {
        "results": [r.as_dict() for r in results],
        "delivered": any(r.ok for r in results),
    }


@router.post("/api/worker/run", tags=["worker"], summary="Run the notification worker now")
def worker_run(_: users_module.User = Depends(auth.require_role("admin", "operator"))) -> dict:
    """Flush pending escalations immediately.

    Safe to call repeatedly: notified items are not sent twice.
    """
    return run_once()


# ------------------------------------------------------ user management

users_router = APIRouter(
    prefix="/api/control/users",
    tags=["users"],
    dependencies=[Depends(auth.require_role("admin"))],
)


@router.get("/api/control/quotations")
def quotations() -> dict:
    """Quotations produced by the Marketing -> Sales -> Accounting pipeline."""
    items = store.list_quotations()
    return {
        "count": len(items),
        "total_value": round(sum(float((i.get("quotation") or {}).get("total") or 0) for i in items), 2),
        "by_status": _count_by(items, "status"),
        "quotations": items,
    }


@users_router.get("")
def list_accounts() -> dict:
    return {
        "users": [u.public() for u in users_module.list_users()],
        "roles": [
            {"id": r, "label": users_module.ROLE_LABELS[r], "description": users_module.ROLE_DESCRIPTIONS[r]}
            for r in users_module.ROLES
        ],
        "min_password_length": users_module.MIN_PASSWORD_LENGTH,
    }


@users_router.post("", status_code=201)
def create_account(payload: NewUser) -> dict:
    """Create a user account. Admin only."""
    try:
        user = users_module.create_user(
            username=payload.username,
            password=payload.password,
            role=payload.role,
            display_name=payload.display_name,
        )
    except users_module.UserError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return user.public()


@users_router.patch("/{username}")
def update_account(username: str, payload: UserUpdate) -> dict:
    """Change role, display name, active flag or password. Admin only."""
    target = users_module.get_user(username)
    if target is None:
        raise HTTPException(status_code=404, detail=f"No user {username!r}")

    # Validate BEFORE mutating, so a rejected request leaves state untouched.
    if payload.active is False and target.is_admin and users_module.active_admin_count() <= 1:
        raise HTTPException(status_code=400, detail="Cannot disable the last active administrator.")
    if payload.role is not None and target.is_admin:
        try:
            new_role = users_module.validate_role(payload.role)
        except users_module.UserError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if new_role != "admin" and users_module.active_admin_count() <= 1:
            raise HTTPException(status_code=400, detail="Cannot demote the last active administrator.")

    try:
        if payload.password:
            if not users_module.set_password(username, payload.password):
                raise HTTPException(status_code=404, detail=f"No user {username!r}")
        user = users_module.update_user(
            username,
            role=payload.role,
            display_name=payload.display_name,
            active=payload.active,
        )
    except users_module.UserError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if user is None:
        raise HTTPException(status_code=404, detail=f"No user {username!r}")
    return user.public()


@users_router.delete("/{username}")
def delete_account(username: str, request_user: users_module.User = Depends(auth.require_panel)) -> dict:
    """Delete an account. Admin only, and you cannot delete yourself."""
    if username.strip().lower() == request_user.username.lower():
        raise HTTPException(status_code=400, detail="You cannot delete your own account.")
    target = users_module.get_user(username)
    if target is None:
        raise HTTPException(status_code=404, detail=f"No user {username!r}")
    if target.is_admin and users_module.active_admin_count() <= 1:
        raise HTTPException(status_code=400, detail="Cannot delete the last active administrator.")
    users_module.delete_user(username)
    return {"deleted": username}


@router.get("/control/users", response_class=HTMLResponse, include_in_schema=False)
def users_page(request_user: users_module.User = Depends(auth.require_panel)) -> HTMLResponse:
    """HTML user-management screen. Admins get the create/edit controls."""
    return HTMLResponse(
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>User accounts — My Team</title></head><body>"
        "<h1>User accounts</h1>"
        f"<p>Signed in as <strong>{request_user.username}</strong> ({request_user.role}).</p>"
        "<p>The full management UI is at <code>/control/settings/users</code>.</p>"
        "</body></html>"
    )