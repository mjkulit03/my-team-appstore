"""Control-panel authentication and role-based access control.

Accounts live in ``users.py``. The session cookie is signed by Starlette's
``SessionMiddleware`` and carries the username; the role is always re-read from
the store on each request, so disabling a user takes effect immediately rather
than at their next login.

If no users exist the panel is *disabled*: guarded routes return 503. A bootstrap
admin is created from ``CONTROL_PANEL_PASSWORD`` so there is always a way in.
"""

from __future__ import annotations

import hmac
import secrets
import time

from fastapi import HTTPException, Request
from starlette.middleware.sessions import SessionMiddleware

import users as users_module
from notifications.config import NotificationSettings, get_settings

SESSION_KEY = "control_user"

# Simple fixed-window limiter: enough to blunt online guessing.
_MAX_ATTEMPTS = 5
_WINDOW_SECONDS = 300
_attempts: dict[str, list[float]] = {}


def add_session_middleware(app, settings: NotificationSettings | None = None) -> None:
    settings = settings or get_settings()
    secret = settings.session_secret or ""
    if not secret:
        # Derive a stable per-process secret so sessions still work locally.
        secret = secrets.token_urlsafe(32)
    app.add_middleware(SessionMiddleware, secret_key=secret, max_age=8 * 60 * 60, same_site="lax")


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def is_rate_limited(request: Request) -> bool:
    now = time.time()
    key = _client_key(request)
    recent = [t for t in _attempts.get(key, []) if now - t < _WINDOW_SECONDS]
    _attempts[key] = recent
    return len(recent) >= _MAX_ATTEMPTS


def record_failure(request: Request) -> None:
    _attempts.setdefault(_client_key(request), []).append(time.time())


def clear_failures(request: Request) -> None:
    _attempts.pop(_client_key(request), None)


# ----------------------------------------------------------------- session


def current_user(request: Request):
    """The signed-in user, or None. Re-reads the store so roles stay current."""
    username = request.session.get(SESSION_KEY)
    if not username:
        return None
    user = users_module.get_user(username)
    if user is None or not user.active:
        request.session.pop(SESSION_KEY, None)
        return None
    return user


def is_authenticated(request: Request) -> bool:
    return current_user(request) is not None


def login(request: Request, username: str) -> None:
    request.session.clear()
    request.session[SESSION_KEY] = username


def logout(request: Request) -> None:
    request.session.clear()


def check_password(candidate: str, settings: NotificationSettings | None = None) -> bool:
    """Legacy single-password check, kept for the bootstrap admin path."""
    settings = settings or get_settings()
    if not settings.panel_enabled:
        return False
    return hmac.compare_digest((candidate or "").encode("utf-8"), settings.panel_password.encode("utf-8"))


def panel_problem(settings: NotificationSettings | None = None) -> str | None:
    """Explain why the panel cannot be opened, if it cannot."""
    settings = settings or get_settings()
    if settings.panel_enabled and len(settings.panel_password) < users_module.MIN_PASSWORD_LENGTH:
        return (
            f"CONTROL_PANEL_PASSWORD must be at least "
            f"{users_module.MIN_PASSWORD_LENGTH} characters."
        )
    if not users_module.list_users():
        return (
            "No user accounts exist yet, so the control panel is disabled. "
            "Set CONTROL_PANEL_PASSWORD (8+ characters) and restart to create the "
            "bootstrap admin, or set SEED_DEMO_USERS=true with DEMO_USER_PASSWORD."
        )
    return None


# ------------------------------------------------------------- guards


def require_panel(request: Request):
    """Dependency for any authenticated control-panel route.

    503 when the panel has no accounts yet (fail closed), 401 when the caller is
    simply not signed in.
    """
    problem = panel_problem()
    if problem:
        raise HTTPException(status_code=503, detail=problem)
    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in to the control panel first.")
    return user


def require_role(*roles: str):
    """Dependency factory guarding routes by role, e.g. ``Depends(require_role("admin"))``."""

    def dependency(request: Request):
        user = require_panel(request)
        if user.role not in roles:
            raise HTTPException(
                status_code=403,
                detail=f"This action needs the {' or '.join(roles)} role; you are signed in as {user.role}.",
            )
        return user

    return dependency