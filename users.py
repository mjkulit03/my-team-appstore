"""Role-based user accounts for the control panel.

Passwords are hashed with PBKDF2-HMAC-SHA256 from the standard library (no bcrypt
dependency). Plaintext passwords are never stored or logged.

Roles, from most to least privileged:

    admin     everything, including creating and disabling other users
    operator  approve/reject escalations, resolve alerts, view leads
    analyst   read-only: view dashboards, traffic and pipelines

A bootstrap admin is guaranteed to exist: if no users have been created yet, the
``CONTROL_PANEL_PASSWORD`` from the environment is turned into an admin account,
so there is always a way in. Demo accounts are seeded only when explicitly enabled.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import store

ROLES = ("admin", "operator", "analyst")
ROLE_LABELS = {
    "admin": "Administrator",
    "operator": "Operator",
    "analyst": "Analyst (read-only)",
}
ROLE_DESCRIPTIONS = {
    "admin": "Full access. Can create, edit, disable and delete user accounts.",
    "operator": "Can approve or reject escalations and resolve alerts. Cannot manage users.",
    "analyst": "Read-only access to dashboards, traffic analysis and pipelines.",
}

MIN_PASSWORD_LENGTH = 8
PBKDF2_ROUNDS = 240_000
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")


class UserError(ValueError):
    """Raised for invalid user input. Surfaces to the client as a 400."""


@dataclass
class User:
    id: str
    username: str
    display_name: str
    role: str
    active: bool
    created_at: str
    password_hash: str = ""
    last_login_at: str | None = None

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    def public(self) -> dict[str, Any]:
        """User data safe to render or return over the API (no hash)."""
        return {
            "id": self.id,
            "username": self.username,
            "display_name": self.display_name,
            "role": self.role,
            "role_label": ROLE_LABELS.get(self.role, self.role),
            "active": self.active,
            "created_at": self.created_at,
            "last_login_at": self.last_login_at,
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------- passwords


def hash_password(password: str, *, rounds: int = PBKDF2_ROUNDS) -> str:
    """Hash a password as ``pbkdf2_sha256$rounds$salt$hash`` (all hex/base64)."""
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        raise UserError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return f"pbkdf2_sha256${rounds}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    """Constant-time password check against a stored hash."""
    try:
        algorithm, rounds, salt_hex, digest_hex = encoded.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        expected = bytes.fromhex(digest_hex)
        candidate = hashlib.pbkdf2_hmac(
            "sha256", (password or "").encode("utf-8"), bytes.fromhex(salt_hex), int(rounds)
        )
        return hmac.compare_digest(candidate, expected)
    except (ValueError, TypeError, AttributeError):
        return False


def validate_username(username: str) -> str:
    value = (username or "").strip().lower()
    if not USERNAME_RE.match(value):
        raise UserError(
            "Username must be 3-32 characters: lowercase letters, numbers, dot, dash or underscore."
        )
    return value


def validate_role(role: str) -> str:
    value = (role or "").strip().lower()
    if value not in ROLES:
        raise UserError(f"Role must be one of: {', '.join(ROLES)}.")
    return value


# ----------------------------------------------------------------- store


def _row_to_user(row: dict[str, Any]) -> User:
    return User(
        id=row.get("id", ""),
        username=row.get("username", ""),
        display_name=row.get("display_name") or row.get("username", ""),
        role=row.get("role", "analyst"),
        active=bool(row.get("active", True)),
        created_at=row.get("created_at", ""),
        password_hash=row.get("password_hash", ""),
        last_login_at=row.get("last_login_at"),
    )


def list_users(include_inactive: bool = True) -> list[User]:
    users = [_row_to_user(r) for r in store._read(store._store_path()).get("users", [])]
    if not include_inactive:
        users = [u for u in users if u.active]
    return sorted(users, key=lambda u: (u.role != "admin", u.username))


def get_user(username: str) -> User | None:
    wanted = (username or "").strip().lower()
    for row in store._read(store._store_path()).get("users", []):
        if row.get("username", "").lower() == wanted:
            return _row_to_user(row)
    return None


def create_user(
    username: str,
    password: str,
    role: str,
    display_name: str = "",
    active: bool = True,
) -> User:
    """Create a user account. Raises UserError on invalid or duplicate input."""
    username = validate_username(username)
    role = validate_role(role)
    if get_user(username) is not None:
        raise UserError(f"A user named {username!r} already exists.")
    password_hash = hash_password(password)
    display_name = (display_name or "").strip() or username

    row = {
        "id": f"usr_{secrets.token_hex(5)}",
        "username": username,
        "display_name": display_name,
        "role": role,
        "active": bool(active),
        "created_at": _now(),
        "password_hash": password_hash,
        "last_login_at": None,
    }

    def apply(data: dict[str, Any]) -> None:
        data.setdefault("users", []).append(row)

    store._mutate(apply)
    return _row_to_user(row)


def update_user(
    username: str,
    *,
    role: str | None = None,
    display_name: str | None = None,
    active: bool | None = None,
) -> User | None:
    username = validate_username(username)
    updated: dict[str, Any] = {}

    def apply(data: dict[str, Any]) -> dict[str, Any] | None:
        rows = data.setdefault("users", [])
        for row in rows:
            if row.get("username", "").lower() == username:
                if role is not None:
                    row["role"] = validate_role(role)
                if display_name is not None:
                    row["display_name"] = display_name.strip() or username
                if active is not None:
                    row["active"] = bool(active)
                return row
        return None

    updated = store._mutate(apply) or {}
    return _row_to_user(updated) if updated else None


def set_password(username: str, new_password: str) -> bool:
    username = validate_username(username)
    password_hash = hash_password(new_password)

    def apply(data: dict[str, Any]) -> bool:
        for row in data.get("users", []):
            if row.get("username", "").lower() == username:
                row["password_hash"] = password_hash
                return True
        return False

    return store._mutate(apply)


def delete_user(username: str) -> bool:
    username = validate_username(username)

    def apply(data: dict[str, Any]) -> bool:
        rows = data.get("users", [])
        for row in rows:
            if row.get("username", "").lower() == username:
                rows.remove(row)
                return True
        return False

    return store._mutate(apply)


def authenticate(username: str, password: str) -> User | None:
    """Verify credentials. Returns the user on success, else None."""
    user = get_user(username)
    if user is None or not user.active:
        # Hash anyway so a missing user and a wrong password take similar time.
        hash_password(password or "x", rounds=1) if password else None
        return None
    if not verify_password(password or "", user.password_hash):
        return None

    def apply(data: dict[str, Any]) -> None:
        for row in data.get("users", []):
            if row.get("username", "").lower() == user.username:
                row["last_login_at"] = _now()

    store._mutate(apply)
    return user


def active_admin_count() -> int:
    return len([u for u in list_users() if u.is_admin and u.active])


# --------------------------------------------------------------- seeding


def ensure_bootstrap_admin() -> User | None:
    """Guarantee at least one admin exists, using CONTROL_PANEL_PASSWORD.

    Runs at startup. If users already exist this does nothing.
    """
    existing = list_users()
    if existing:
        return None
    password = os.getenv("CONTROL_PANEL_PASSWORD", "").strip()
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        return None
    return create_user(
        username=os.getenv("CONTROL_PANEL_ADMIN_USER", "admin").strip() or "admin",
        password=password,
        role="admin",
        display_name="Bootstrap Administrator",
    )


def seed_demo_users() -> list[str]:
    """Create the demo accounts documented in the runbook.

    Only runs when ``SEED_DEMO_USERS=true``. Passwords come from
    ``DEMO_USER_PASSWORD`` so they are never hardcoded.
    """
    if (os.getenv("SEED_DEMO_USERS", "").strip().lower() not in {"1", "true", "yes", "on"}):
        return []
    password = os.getenv("DEMO_USER_PASSWORD", "").strip()
    if len(password) < MIN_PASSWORD_LENGTH:
        return []

    demo = [
        ("admin", "admin", "Avery Dela Cruz", "Administrator"),
        ("operator", "operator", "Sam Santos", "Operator"),
        ("analyst", "analyst", "Jae Rivera", "Analyst"),
    ]
    created = []
    for username, role, display_name, _label in demo:
        if get_user(username) is None:
            create_user(username, password, role, display_name)
            created.append(username)
    return created