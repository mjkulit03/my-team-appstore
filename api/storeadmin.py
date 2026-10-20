"""Store-content editor behind the control-panel login.

This is the username-and-password replacement for the GitHub-token dialog on the
static site. The FastAPI app authenticates the administrator with the same
accounts as the rest of the control panel, writes ``docs/store-content.json`` and
rebuilds ``docs/index.html`` in the same request, so the store is updated without
any credential ever reaching a browser.

Two credentials exist, and neither is a browser token:

- the administrator's username and password, checked by ``users``/``auth``;
- optionally, ``STORE_GITHUB_TOKEN`` in the server's environment (see
  ``store_publish``), used to push the same file to the exact repository GitHub
  Pages publishes from.

Publishing is best-effort: a rejected push never loses a save that already
succeeded locally.
"""

from __future__ import annotations

import urllib.parse
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import auth
import catalog
import store_content
import store_publish
import users as users_module

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

EDITOR_URL = "/control/store"
#: Prices are commercial decisions, so this is the same pair that may approve a
#: quotation or resolve an escalation elsewhere in the panel.
EDITOR_ROLES = ("admin", "operator")


def _copy_values(document: dict) -> dict[str, str]:
    """Page copy as stored, before ``{count}`` substitution.

    The editor shows the template text so an administrator can keep or move the
    placeholder; the published page is the thing that resolves it.
    """
    stored = document.get("copy") or {}
    return {
        key: stored.get(key) or default
        for key, default in store_content.PAGE_COPY_DEFAULTS.items()
    }


def _render(
    request: Request,
    user: users_module.User,
    values: dict | None = None,
    notice: str = "",
    error: str = "",
    status_code: int = 200,
) -> HTMLResponse:
    document = store_content.load()
    products = values["products"] if values else store_content.apply(catalog.list_products(), document)
    copy = values["copy"] if values else _copy_values(document)
    return templates.TemplateResponse(
        request,
        "storeadmin.html",
        {
            "me": user,
            "products": products,
            "copy": copy,
            "copy_fields": list(store_content.COPY_LABELS.items()),
            "max_text": store_content.MAX_TEXT,
            "max_copy": store_content.MAX_COPY,
            "max_price": store_content.MAX_PRICE,
            "notice": notice,
            "error": error,
            "publishing": store_publish.configured(),
            "mirror_repo": store_publish.repo(),
            "can_edit": user.role in EDITOR_ROLES,
        },
        status_code=status_code,
    )


def _require_editor(request: Request):
    """The signed-in user, or a redirect response to send them to the login."""
    user = auth.current_user(request)
    if user is None:
        return None, RedirectResponse(
            url=f"/control/login?next={urllib.parse.quote(EDITOR_URL, safe='')}",
            status_code=303,
        )
    return user, None


# --------------------------------------------------------------- the page


@router.get(EDITOR_URL, response_class=HTMLResponse)
def store_editor(request: Request, notice: str = "", error: str = "") -> HTMLResponse:
    """The editor form. Signing in is required; the login screen comes back here."""
    user, redirect = _require_editor(request)
    if redirect is not None:
        return redirect
    return _render(request, user, notice=notice, error=error)


@router.post(EDITOR_URL, response_class=HTMLResponse)
async def save_store(request: Request) -> HTMLResponse:
    """Validate the submitted form, save it and rebuild the store page."""
    user, redirect = _require_editor(request)
    if redirect is not None:
        return redirect
    if user.role not in EDITOR_ROLES:
        return _render(
            request,
            user,
            error=f"Changing prices needs the {' or '.join(EDITOR_ROLES)} role; you are signed in as {user.role}.",
            status_code=403,
        )

    form = await request.form()
    document = _document_from_form(form)
    problems = store_content.validate(document)
    if problems:
        summary = problems[0] if len(problems) == 1 else f"{problems[0]} ({len(problems) - 1} more problem(s).)"
        return _render(
            request,
            user,
            values=_submitted_values(form),
            error=summary,
            status_code=400,
        )

    clean = store_content.normalize(document)
    store_content.save(clean)

    notice = "Saved. The store page was rebuilt."
    try:
        _rebuild()
    except Exception as exc:  # a rebuild failure must not look like a save failure
        notice = f"Saved, but the page could not be rebuilt: {exc}"

    if store_publish.configured():
        try:
            store_publish.publish(clean)
            notice += " Pushed to GitHub; the public mirror updates in about a minute."
        except Exception as exc:
            notice += f" The local store is updated, but the GitHub mirror is not: {exc}"

    query = urllib.parse.urlencode({"notice": notice})
    return RedirectResponse(url=f"{EDITOR_URL}?{query}", status_code=303)


# ------------------------------------------------------------ form mapping


def _document_from_form(form) -> dict:
    """Build a content document from the submitted fields.

    A blank field means "use the catalog value", and a field that still equals the
    catalog value is left out entirely, so the saved file stays a short list of
    actual overrides rather than a frozen copy of the defaults.
    """
    document: dict = {
        "version": store_content.CONTENT_VERSION,
        "prices": {},
        "labels": {},
        "copy": {},
    }

    for product in catalog.list_products():
        slug = product["slug"]
        labels = {}
        for key in store_content.LABEL_KEYS:
            raw = (form.get(f"product.{slug}.{key}") or "").strip()
            if raw and raw != str(product[key]):
                labels[key] = raw
        if labels:
            document["labels"][slug] = labels

        prices = {}
        for key in store_content.PRICE_KEYS:
            raw = (form.get(f"product.{slug}.{key}") or "").strip()
            if not raw:
                continue
            submitted = store_content._clean_price(raw)
            if submitted is None or submitted != int(product[key]):
                prices[key] = raw
        if prices:
            document["prices"][slug] = prices

    for key, default in store_content.PAGE_COPY_DEFAULTS.items():
        raw = (form.get(f"copy.{key}") or "").strip()
        if raw and raw != default:
            document["copy"][key] = raw

    return document


def _submitted_values(form) -> dict:
    """The form as typed, so a rejected save does not throw away the edit."""
    products = []
    for product in catalog.list_products():
        slug = product["slug"]
        row = {"slug": slug, "icon": product.get("icon", ""), "features": product.get("features", [])}
        for key in store_content.LABEL_KEYS + store_content.PRICE_KEYS:
            raw = (form.get(f"product.{slug}.{key}") or "").strip()
            row[key] = raw or str(product[key])
        products.append(row)

    copy = {}
    for key, default in store_content.PAGE_COPY_DEFAULTS.items():
        raw = (form.get(f"copy.{key}") or "").strip()
        copy[key] = raw or default
    return {"products": products, "copy": copy}


def _rebuild() -> None:
    """Re-render ``docs/index.html`` from the catalog plus the new overrides."""
    from tools.build_store import build

    build()
