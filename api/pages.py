"""Server-rendered storefront pages and the control-panel login screen.

Templates live in ``templates/``. Jinja2 autoescaping is on, so catalog copy and
AI-drafted text are never interpreted as markup.
"""

from __future__ import annotations

import os
import urllib.parse

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import auth
import catalog
import currency
import store
import traffic
import users as users_module
from orchestrator import run_quotation_pipeline
from notifications.config import get_settings
from notifications.escalations import build_campaign_escalation
from notifications.worker import run_once
from agents import run_marketing_agent

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    traffic.record_view("/", referrer=request.headers.get("referer", ""))
    products = catalog.list_products()
    code = currency.base_currency()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "products": products,
            "categories": catalog.list_categories(),
            "total_monthly": sum(p["price_month"] for p in products),
            "currency": code,
            "symbol": currency.symbol(code),
            "usd_total": currency.format_money(
                currency.convert(sum(p["price_month"] for p in products), code, "USD"), "USD"
            ),
            "usd_month": {
                p["slug"]: currency.format_money(
                    currency.convert(p["price_month"], code, "USD"), "USD"
                )
                for p in products
            },
        },
    )


@router.get("/products/{slug}", response_class=HTMLResponse)
def product_page(request: Request, slug: str) -> HTMLResponse:
    product = catalog.find_product(slug)
    if product is None:
        raise HTTPException(status_code=404, detail=f"No product with slug {slug!r}")

    traffic.record_view(
        f"/products/{slug}", product_slug=slug, referrer=request.headers.get("referer", "")
    )

    # The Marketing AI drafts the social copy shown on the landing page.
    marketing = run_marketing_agent(
        product_description=product["description"],
        product_name=product["name"],
        tone="confident",
    )
    code = currency.base_currency()
    usd_month = currency.format_money(
        currency.convert(product["price_month"], code, "USD"), "USD"
    )
    return templates.TemplateResponse(
        request,
        "product.html",
        {
            "product": product,
            "marketing": marketing,
            "submitted": False,
            "currency": code,
            "symbol": currency.symbol(code),
            "usd_month": usd_month,
        },
    )


@router.post("/products/{slug}/inquiry", response_class=HTMLResponse)
def submit_inquiry(
    request: Request,
    slug: str,
    contact_name: str = Form(...),
    email: str = Form(...),
    organisation: str = Form(""),
    message: str = Form(""),
    seats: int = Form(1),
) -> HTMLResponse:
    product = catalog.find_product(slug)
    if product is None:
        raise HTTPException(status_code=404, detail=f"No product with slug {slug!r}")

    settings = get_settings()
    seats = max(1, seats)
    estimated_value = round((product["price_month"] + product["price_setup"]) * 12 * (seats / 10.0), 2)
    code = currency.base_currency()
    traffic.record_inquiry(f"/products/{slug}/inquiry", slug)

    lead = store.create_lead(
        product_slug=product["slug"],
        product_name=product["name"],
        contact_name=contact_name.strip(),
        email=email.strip(),
        organisation=organisation.strip(),
        message=message.strip(),
        seats=seats,
        estimated_value=estimated_value,
    )

    from notifications.escalations import build_lead_escalation

    escalation = build_lead_escalation(lead, settings)
    if escalation:
        store.create_escalation(**escalation.as_dict())

    marketing = run_marketing_agent(
        product_description=product["description"],
        product_name=product["name"],
        tone="confident",
    )
    return templates.TemplateResponse(
        request,
        "product.html",
        {
            "product": product,
            "marketing": marketing,
            "submitted": True,
            "estimated_value": estimated_value,
            "value_display": currency.format_money(estimated_value, code),
            "currency": code,
            "symbol": currency.symbol(code),
            "usd_month": currency.format_money(
                currency.convert(product["price_month"], code, "USD"), "USD"
            ),
        },
    )


@router.get("/control/campaigns/{slug}", response_class=HTMLResponse)
def campaign_page(request: Request, slug: str) -> HTMLResponse:
    """Approve or reject AI-drafted marketing copy for one product."""
    if not auth.is_authenticated(request):
        return RedirectResponse(url="/control/login", status_code=303)

    product = catalog.find_product(slug)
    if product is None:
        raise HTTPException(status_code=404, detail=f"No product with slug {slug!r}")

    campaign = run_marketing_agent(
        product_description=product["description"],
        product_name=product["name"],
        brand=product["name"],
        tone="confident",
    )
    escalation = build_campaign_escalation(product, campaign, get_settings())
    pending = [e for e in store.list_escalations("pending") if e.get("product_slug") == slug]
    return templates.TemplateResponse(
        request,
        "campaign.html",
        {"product": product, "campaign": campaign, "escalation": escalation, "pending": pending},
    )


# ------------------------------------------------------------- login


@router.post("/products/{slug}/quotation", response_class=HTMLResponse)
def submit_quotation(
    request: Request,
    slug: str,
    name: str = Form(...),
    email: str = Form(...),
    organisation: str = Form(""),
    message: str = Form(""),
    seats: int = Form(1),
    term_months: int = Form(12),
    discount_pct: float = Form(0.0),
    support: bool = Form(False),
) -> HTMLResponse:
    """Run the AI pipeline and show the resulting quotation."""
    product = catalog.find_product(slug)
    if product is None:
        raise HTTPException(status_code=404, detail=f"No product with slug {slug!r}")

    error = ""
    result = None
    try:
        result = run_quotation_pipeline(
            product,
            {
                "name": name,
                "email": email,
                "organisation": organisation,
                "message": message,
            },
            seats=seats,
            term_months=term_months,
            discount_pct=discount_pct,
            support=support,
        )
    except ValueError as exc:
        error = str(exc)

    return templates.TemplateResponse(
        request,
        "quotation.html",
        {
            "product": product,
            "result": result,
            "error": error,
            "currency": currency.base_currency(),
            "symbol": currency.symbol(),
        },
    )


@router.get("/quotations/{quotation_id}", response_class=HTMLResponse)
def quotation_page(request: Request, quotation_id: str) -> HTMLResponse:
    """Printable view of a stored quotation."""
    record = store.get_quotation(quotation_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No quotation {quotation_id!r}")
    product = catalog.find_product(record["product_slug"]) or {}
    return templates.TemplateResponse(
        request,
        "quotation.html",
        {
            "product": product,
            "record": record,
            "result": None,
            "error": "",
            "currency": currency.base_currency(),
            "symbol": currency.symbol(),
        },
    )


@router.get("/control/login", response_class=HTMLResponse)
def login_form(request: Request, error: str = "", next: str = "") -> HTMLResponse:
    problem = auth.panel_problem()
    demo = os.getenv("SEED_DEMO_USERS", "").strip().lower() in {"1", "true", "yes", "on"}
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "error": error,
            "problem": problem,
            "demo_enabled": demo,
            "next": _safe_next(next),
        },
    )


@router.post("/control/login", response_model=None)
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form(""),
) -> HTMLResponse | RedirectResponse:
    problem = auth.panel_problem()
    if problem:
        return templates.TemplateResponse(
            request, "login.html", {"error": "", "problem": problem, "demo_enabled": False, "next": ""}
        )
    if auth.is_rate_limited(request):
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "error": "Too many attempts. Try again in a few minutes.",
                "problem": None,
                "demo_enabled": False,
                "next": _safe_next(next),
            },
        )

    user = users_module.authenticate(username, password)
    if user is not None:
        auth.clear_failures(request)
        auth.login(request, user.username)
        return RedirectResponse(url=_safe_next(next) or "/control/overview", status_code=303)

    auth.record_failure(request)
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "error": "Incorrect username or password.",
            "problem": None,
            "demo_enabled": False,
            "next": _safe_next(next),
        },
    )


def _safe_next(target: str) -> str:
    """Only local control-panel destinations, so `next` cannot become an open redirect."""
    candidate = (target or "").strip()
    if not candidate.startswith("/control/") or candidate.startswith("//"):
        return ""
    return candidate


# --------------------------------------------------- user management page


@router.get("/control/settings/users", response_class=HTMLResponse)
def user_settings(request: Request, error: str = "", notice: str = "") -> HTMLResponse:
    """Admin-only screen for creating and managing user accounts."""
    user = auth.current_user(request)
    if user is None:
        return RedirectResponse(url="/control/login", status_code=303)
    if user.role != "admin":
        return templates.TemplateResponse(
            request,
            "users.html",
            {
                "error": "Only administrators can manage user accounts.",
                "notice": "",
                "accounts": [],
                "roles": [],
                "is_admin": False,
                "me": user,
                "min_password": users_module.MIN_PASSWORD_LENGTH,
            },
        )

    try:
        return templates.TemplateResponse(
            request,
            "users.html",
            {
                "error": error,
                "notice": notice,
                "accounts": [u.public() for u in users_module.list_users()],
                "roles": [
                    {"id": r, "label": users_module.ROLE_LABELS[r], "description": users_module.ROLE_DESCRIPTIONS[r]}
                    for r in users_module.ROLES
                ],
                "is_admin": True,
                "me": user,
                "min_password": users_module.MIN_PASSWORD_LENGTH,
            },
        )
    except users_module.UserError as exc:
        return templates.TemplateResponse(
            request,
            "users.html",
            {"error": str(exc), "notice": "", "accounts": [], "roles": [], "is_admin": False,
             "me": user, "min_password": users_module.MIN_PASSWORD_LENGTH},
        )


@router.post("/control/settings/users/create")
def create_user_page(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form("analyst"),
    display_name: str = Form(""),
) -> RedirectResponse:
    user = auth.current_user(request)
    if user is None:
        return RedirectResponse(url="/control/login", status_code=303)
    if user.role != "admin":
        return RedirectResponse(url="/control/settings/users", status_code=303)
    try:
        users_module.create_user(username, password, role, display_name)
    except users_module.UserError as exc:
        return RedirectResponse(
            url=f"/control/settings/users?error={urllib.parse.quote(str(exc))}", status_code=303
        )
    return RedirectResponse(
        url=f"/control/settings/users?notice={urllib.parse.quote('Created ' + username.strip().lower())}",
        status_code=303,
    )


@router.post("/control/settings/users/{username}/toggle")
def toggle_user_page(request: Request, username: str) -> RedirectResponse:
    user = auth.current_user(request)
    if user is None or user.role != "admin":
        return RedirectResponse(url="/control/login", status_code=303)
    target = users_module.get_user(username)
    if target is None:
        return RedirectResponse(url="/control/settings/users?error=No+such+user", status_code=303)
    if target.active and target.is_admin and users_module.active_admin_count() <= 1:
        return RedirectResponse(
            url="/control/settings/users?error=Cannot+disable+the+last+administrator", status_code=303
        )
    users_module.update_user(username, active=not target.active)
    return RedirectResponse(url="/control/settings/users", status_code=303)


@router.post("/control/settings/users/{username}/role")
def change_role_page(request: Request, username: str, role: str = Form(...)) -> RedirectResponse:
    user = auth.current_user(request)
    if user is None or user.role != "admin":
        return RedirectResponse(url="/control/login", status_code=303)
    try:
        users_module.update_user(username, role=role)
    except users_module.UserError as exc:
        return RedirectResponse(
            url=f"/control/settings/users?error={urllib.parse.quote(str(exc))}", status_code=303
        )
    return RedirectResponse(url="/control/settings/users", status_code=303)


@router.post("/control/settings/users/{username}/password")
def set_password_page(
    request: Request, username: str, password: str = Form(...)
) -> RedirectResponse:
    admin = auth.current_user(request)
    if admin is None or admin.role != "admin":
        return RedirectResponse(url="/control/login", status_code=303)
    try:
        users_module.set_password(username, password)
    except users_module.UserError as exc:
        return RedirectResponse(
            url=f"/control/settings/users?error={urllib.parse.quote(str(exc))}", status_code=303
        )
    return RedirectResponse(
        url=f"/control/settings/users?notice={urllib.parse.quote('Password updated for ' + username)}",
        status_code=303,
    )


@router.post("/control/escalations/{escalation_id}/resolve")
def resolve_escalation_form(
    request: Request,
    escalation_id: str,
    resolution: str = Form("approved"),
    note: str = Form(""),
) -> RedirectResponse:
    """Record a human decision on an escalation."""
    if not auth.is_authenticated(request):
        return RedirectResponse(url="/control/login", status_code=303)
    if resolution not in {"approved", "rejected", "deferred"}:
        resolution = "deferred"
    store.resolve_escalation(escalation_id, note.strip(), resolution)
    return RedirectResponse(url="/control/overview", status_code=303)


@router.get("/control/logout")
def logout(request: Request) -> RedirectResponse:
    auth.logout(request)
    return RedirectResponse(url="/", status_code=303)


@router.get("/control/overview", response_class=HTMLResponse)
def control_overview(request: Request) -> HTMLResponse:
    if not auth.is_authenticated(request):
        return RedirectResponse(url="/control/login", status_code=303)

    settings = get_settings()
    escalations = store.list_escalations()
    leads = store.list_leads()
    return templates.TemplateResponse(
        request,
        "overview.html",
        {
            "escalations": escalations,
            "pending": [e for e in escalations if e["status"] == "pending"],
            "leads": leads,
            "products": catalog.list_products(),
            "status": settings.public_status(),
            "total_value": sum(float(l.get("estimated_value") or 0) for l in leads),
            "worker": run_once(dry_run=True),
            "traffic": traffic.summary(),
            "currency": currency.base_currency(),
            "currency_symbol": currency.symbol(),
            "me": auth.current_user(request),
            "quotations": store.list_quotations()[:8],
            "quote_total": sum(
                float((q.get("quotation") or {}).get("total") or 0) for q in store.list_quotations()
            ),
        },
    )