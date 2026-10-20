"""Tests for PHP currency handling and role-based user management."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import catalog
import currency
import store
import users
from main import app

PASSWORD = "test-control-password"


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    for key in ("BASE_CURRENCY", "FX_USD", "LEAD_VALUE_THRESHOLD",
                "ACCOUNTING_ANOMALY_THRESHOLD", "SEED_DEMO_USERS",
                "DEMO_USER_PASSWORD", "CONTROL_PANEL_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    store.reset_for_tests()
    yield
    store.reset_for_tests()


@pytest.fixture
def admin(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    users.create_user("boss", PASSWORD, "admin", "Boss Admin")
    c = TestClient(app)
    c.post("/control/login", data={"username": "boss", "password": PASSWORD}, follow_redirects=False)
    return c


def login_as(username: str, password: str, monkeypatch) -> TestClient:
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    c = TestClient(app)
    c.post("/control/login", data={"username": username, "password": password}, follow_redirects=False)
    return c


# --------------------------------------------------------------- currency


def test_base_currency_defaults_to_php(monkeypatch):
    monkeypatch.delenv("BASE_CURRENCY", raising=False)
    assert currency.base_currency() == "PHP"
    assert currency.symbol("PHP") == "₱"
    assert currency.format_money(1490) == "₱1,490.00"


def test_base_currency_is_overridable(monkeypatch):
    monkeypatch.setenv("BASE_CURRENCY", "USD")
    assert currency.base_currency() == "USD"
    monkeypatch.setenv("BASE_CURRENCY", "XYZ")  # unsupported -> falls back
    assert currency.base_currency() == "PHP"


def test_conversion_round_trips_through_php():
    php = 1000
    usd = currency.convert(php, "PHP", "USD")
    assert usd is not None and usd > 0
    back = currency.convert(usd, "USD", "PHP")
    assert back == pytest.approx(php, rel=0.01)


def test_conversion_of_identical_currency_is_identity():
    assert currency.convert(1234.56, "PHP", "PHP") == 1234.56


def test_conversion_rejects_unknown_currency():
    assert currency.convert(100, "PHP", "XYZ") is None
    assert currency.convert(100, "ZZZ", "PHP") is None


def test_fx_rate_can_be_overridden(monkeypatch):
    monkeypatch.setenv("FX_USD", "0.02")
    assert currency.rate("USD") == 0.02
    assert currency.convert(100, "PHP", "USD") == 2.0


def test_fx_override_ignores_bad_values(monkeypatch):
    monkeypatch.setenv("FX_USD", "not-a-number")
    assert currency.rate("USD") == currency.DEFAULT_RATES["USD"]


def test_format_dual_shows_peso_and_usd():
    out = currency.format_dual(1490, "PHP")
    assert "₱1,490.00" in out
    assert "$" in out


def test_catalog_prices_are_php_and_convertible():
    for product in catalog.list_products():
        price = currency.catalog_price(product["price_month"])
        assert price["currency"] == "PHP"
        assert price["symbol"] == "₱"
        assert price["usd_equivalent"] and price["usd_equivalent"] > 0
        # A peso price must be far larger than its USD equivalent.
        assert product["price_month"] > price["usd_equivalent"]


def test_storefront_shows_peso():
    html = TestClient(app).get("/").text
    assert "₱" in html
    assert "$" in html  # USD equivalent shown alongside


def test_product_page_shows_peso():
    html = TestClient(app).get("/products/hardware-inventory-system").text
    assert "₱1,490" in html


def test_currency_api_reports_rates(admin):
    body = admin.get("/api/control/currency").json()
    assert body["base_currency"] == "PHP"
    assert body["rates"]["PHP"] == 1.0
    assert "₱" in body["usd_example"]


def test_accounting_accepts_peso_currency():
    body = TestClient(app).post(
        "/api/accounting/report",
        json={"entries": [{"type": "income", "amount": 5000, "category": "Revenue"}],
              "currency": "PHP"},
    ).json()
    assert body["currency"] == "PHP"


# ----------------------------------------------------------------- users


def test_password_hashing_never_stores_plaintext():
    encoded = users.hash_password("supersecret123")
    assert "supersecret123" not in encoded
    assert encoded.startswith("pbkdf2_sha256$")
    assert users.verify_password("supersecret123", encoded)
    assert not users.verify_password("wrong-password", encoded)


def test_password_hash_is_salted():
    a = users.hash_password("same-password-1")
    b = users.hash_password("same-password-1")
    assert a != b  # different salts
    assert users.verify_password("same-password-1", a)
    assert users.verify_password("same-password-1", b)


def test_short_password_is_rejected():
    with pytest.raises(users.UserError):
        users.hash_password("short")


def test_create_user_validates_input():
    users.create_user("valid.user", PASSWORD, "admin")
    with pytest.raises(users.UserError):
        users.create_user("valid.user", PASSWORD, "admin")  # duplicate
    with pytest.raises(users.UserError):
        users.create_user("ab", PASSWORD, "admin")  # too short
    with pytest.raises(users.UserError):
        users.create_user("Bad Name", PASSWORD, "admin")  # invalid chars
    with pytest.raises(users.UserError):
        users.create_user("someone", PASSWORD, "superuser")  # bad role


def test_user_public_view_excludes_hash():
    user = users.create_user("hashcheck", PASSWORD, "analyst")
    assert "password_hash" not in user.public()
    assert user.public()["role_label"] == "Analyst (read-only)"


def test_authenticate_flow():
    users.create_user("jose", PASSWORD, "operator")
    assert users.authenticate("jose", PASSWORD) is not None
    assert users.authenticate("jose", "wrong") is None
    assert users.authenticate("ghost", PASSWORD) is None


def test_disabled_user_cannot_authenticate():
    users.create_user("gone", PASSWORD, "analyst")
    users.update_user("gone", active=False)
    assert users.authenticate("gone", PASSWORD) is None


def test_last_login_is_recorded():
    users.create_user("jose", PASSWORD, "operator")
    assert users.get_user("jose").last_login_at is None
    users.authenticate("jose", PASSWORD)
    assert users.get_user("jose").last_login_at is not None


def test_bootstrap_admin_created_from_env(monkeypatch):
    monkeypatch.setenv("CONTROL_PANEL_PASSWORD", PASSWORD)
    created = users.ensure_bootstrap_admin()
    assert created is not None and created.role == "admin"
    # Idempotent: a second call does not duplicate.
    assert users.ensure_bootstrap_admin() is None
    assert len(users.list_users()) == 1


def test_demo_users_are_seeded_only_when_enabled(monkeypatch):
    monkeypatch.setenv("DEMO_USER_PASSWORD", PASSWORD)
    monkeypatch.delenv("SEED_DEMO_USERS", raising=False)
    assert users.seed_demo_users() == []

    monkeypatch.setenv("SEED_DEMO_USERS", "true")
    assert sorted(users.seed_demo_users()) == ["admin", "analyst", "operator"]
    assert len(users.list_users()) == 3
    assert users.authenticate("operator", PASSWORD).role == "operator"


def test_demo_admin_is_not_shadowed_by_bootstrap(monkeypatch):
    """Regression: bootstrap ran first and stole the `admin` username, so the
    documented demo password did not work for the demo admin."""
    monkeypatch.setenv("DEMO_USER_PASSWORD", PASSWORD)
    monkeypatch.setenv("SEED_DEMO_USERS", "true")
    monkeypatch.setenv("CONTROL_PANEL_PASSWORD", "a-different-bootstrap-pass")

    # Same order as the application lifespan handler.
    users.seed_demo_users()
    users.ensure_bootstrap_admin()

    signed_in = users.authenticate("admin", PASSWORD)
    assert signed_in is not None, "demo admin must sign in with DEMO_USER_PASSWORD"
    assert signed_in.role == "admin"


def test_demo_seeding_requires_a_password(monkeypatch):
    monkeypatch.setenv("SEED_DEMO_USERS", "true")
    monkeypatch.delenv("DEMO_USER_PASSWORD", raising=False)
    assert users.seed_demo_users() == []


# ------------------------------------------------------------- role based


def test_admin_can_manage_users(admin):
    body = admin.get("/api/control/users").json()
    assert body["users"][0]["username"] == "boss"
    assert {r["id"] for r in body["roles"]} == {"admin", "operator", "analyst"}

    created = admin.post(
        "/api/control/users",
        json={"username": "newop", "password": "another-pass-1", "role": "operator"},
    )
    assert created.status_code == 201
    assert created.json()["username"] == "newop"
    assert users.authenticate("newop", "another-pass-1") is not None


def test_analyst_cannot_manage_users(monkeypatch):
    users.create_user("reader", PASSWORD, "analyst")
    c = login_as("reader", PASSWORD, monkeypatch)
    assert c.get("/api/control/overview").status_code == 200  # can read
    assert c.get("/api/control/users").status_code == 403
    assert c.post("/api/control/users", json={
        "username": "sneaky", "password": "another-pass-1", "role": "admin"
    }).status_code == 403


def test_operator_can_resolve_but_not_manage_users(monkeypatch):
    users.create_user("ops", PASSWORD, "operator")
    c = login_as("ops", PASSWORD, monkeypatch)
    escalation = store.create_escalation(
        kind="high_value_lead", severity="high", title="T", summary="S"
    )
    resolved = c.post(
        f"/api/control/escalations/{escalation['id']}/resolve",
        json={"note": "ok", "resolution": "approved"},
    )
    assert resolved.status_code == 200
    assert c.get("/api/control/users").status_code == 403


def test_analyst_cannot_resolve_escalations(monkeypatch):
    users.create_user("reader", PASSWORD, "analyst")
    c = login_as("reader", PASSWORD, monkeypatch)
    escalation = store.create_escalation(
        kind="high_value_lead", severity="high", title="T", summary="S"
    )
    resp = c.post(
        f"/api/control/escalations/{escalation['id']}/resolve",
        json={"note": "ok", "resolution": "approved"},
    )
    assert resp.status_code == 403


def test_cannot_disable_or_delete_last_admin(admin):
    users.create_user("boss2", PASSWORD, "admin")
    admin.delete("/api/control/users/boss2")  # removing another admin is fine
    resp = admin.patch("/api/control/users/boss", json={"active": False})
    assert resp.status_code == 400
    assert "last active administrator" in resp.json()["detail"]
    # The rejected request must not have disabled the account anyway.
    assert users.get_user("boss").active is True


def test_cannot_demote_the_last_admin(admin):
    resp = admin.patch("/api/control/users/boss", json={"role": "analyst"})
    assert resp.status_code == 400
    assert users.get_user("boss").role == "admin"


def test_can_disable_another_admin(admin):
    users.create_user("boss2", PASSWORD, "admin")
    resp = admin.patch("/api/control/users/boss2", json={"active": False})
    assert resp.status_code == 200
    assert users.get_user("boss2").active is False


def test_admin_cannot_delete_self(admin):
    resp = admin.delete("/api/control/users/boss")
    assert resp.status_code == 400
    assert "your own account" in resp.json()["detail"]


def test_disabling_a_user_takes_effect_immediately(monkeypatch):
    users.create_user("temp", PASSWORD, "analyst")
    c = login_as("temp", PASSWORD, monkeypatch)
    assert c.get("/api/control/overview").status_code == 200
    # Role is re-read from the store, not trusted from the session cookie.
    users.update_user("temp", active=False)
    assert c.get("/api/control/overview").status_code == 401


def test_role_change_takes_effect_immediately(monkeypatch):
    users.create_user("promote", PASSWORD, "analyst")
    c = login_as("promote", PASSWORD, monkeypatch)
    assert c.get("/api/control/users").status_code == 403
    users.update_user("promote", role="admin")
    assert c.get("/api/control/users").status_code == 200


def test_user_settings_page_requires_admin(monkeypatch):
    assert TestClient(app).get("/control/settings/users", follow_redirects=False).status_code in (302, 303)
    users.create_user("reader", PASSWORD, "analyst")
    c = login_as("reader", PASSWORD, monkeypatch)
    page = c.get("/control/settings/users")
    assert page.status_code == 200
    assert "cannot manage accounts" in page.text


def test_admin_settings_page_lists_accounts(admin):
    html = admin.get("/control/settings/users").text
    assert "Create an account" in html
    assert "boss" in html
    assert "Operator" in html and "Analyst (read-only)" in html


def test_create_user_through_the_page(admin):
    resp = admin.post(
        "/control/settings/users/create",
        data={"username": "pageuser", "password": "page-pass-123",
              "role": "operator", "display_name": "Page User"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert users.get_user("pageuser").role == "operator"


def test_create_user_page_reports_errors(admin):
    admin.post("/control/settings/users/create",
               data={"username": "pageuser", "password": "page-pass-123", "role": "operator"},
               follow_redirects=False)
    resp = admin.get("/control/settings/users?error=already+exists")
    assert "already exists" in resp.text


def test_weak_username_via_api_is_400(admin):
    resp = admin.post("/api/control/users", json={
        "username": "No Spaces", "password": "long-enough-pass", "role": "analyst"
    })
    assert resp.status_code == 400