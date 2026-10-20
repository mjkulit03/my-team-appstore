"""Tests for the storefront, control panel, notification pipeline and deploy config."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import catalog
import notifications.config as notify_config
import notifications.worker as worker
import store
import traffic
import users
from main import app

ROOT = Path(__file__).resolve().parent.parent
PASSWORD = "test-control-password"


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    """Point persistence at a temp dir and reset escalations before each test."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    store.reset_for_tests()
    yield
    store.reset_for_tests()


@pytest.fixture
def client(monkeypatch):
    """An anonymous client. Creates an admin so the panel is not locked shut."""
    monkeypatch.setenv("CONTROL_PANEL_PASSWORD", PASSWORD)
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret")
    monkeypatch.delenv("NOTIFY_ENABLED", raising=False)
    users.ensure_bootstrap_admin()
    return TestClient(app)


def signed_in_client(monkeypatch, username: str = "admin") -> TestClient:
    """A client with a real account created and already signed in."""
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret")
    users.create_user(username, PASSWORD, "admin", username.title())
    c = TestClient(app)
    c.post(
        "/control/login",
        data={"username": username, "password": PASSWORD},
        follow_redirects=False,
    )
    return c


@pytest.fixture
def signed_in_client_pass(monkeypatch):
    """A client that is already signed in as admin, for control-panel routes."""
    return signed_in_client(monkeypatch)


# ------------------------------------------------------------------ catalog


def test_catalog_has_every_system_for_sale():
    assert len(catalog.list_products()) == 13


def test_every_requested_application_is_in_the_catalog():
    """The seller's eleven applications must all be purchasable."""
    slugs = {p["slug"] for p in catalog.list_products()}
    for slug in (
        "it-asset-management-system",
        "hris",
        "project-management-system",
        "offsite-login-timekeeping-system",
        "offline-pos-system",
        "office-supplies-inventory-system",
        "clinic-inventory-system",
        "student-record-facial-recognition-system",
        "cybersecurity-games",
        "file-tracking-system",
        "hardware-inventory-system",
    ):
        assert slug in slugs, slug


def test_every_product_is_complete_and_uniquely_addressed():
    slugs = [p["slug"] for p in catalog.list_products()]
    assert len(slugs) == len(set(slugs))
    required = {
        "slug", "name", "tagline", "description", "audience", "category",
        "icon", "price_month", "price_setup", "lead_value", "features", "highlights",
    }
    for product in catalog.list_products():
        missing = required - set(product)
        assert not missing, f"{product.get('slug')} missing {missing}"
        assert len(product["description"]) > 80
        assert len(product["features"]) >= 3
        assert product["price_month"] > 0


def test_products_are_findable_by_slug_case_insensitively():
    assert catalog.find_product("hardware-inventory-system") is not None
    assert catalog.find_product("HARDWARE-INVENTORY-SYSTEM") is not None
    assert catalog.find_product("does-not-exist") is None


def test_product_descriptions_are_good_marketing_input():
    """Every description must satisfy the Marketing agent's input contract."""
    from agents import run_marketing_agent

    for product in catalog.list_products():
        result = run_marketing_agent(
            product_description=product["description"],
            product_name=product["name"],
        )
        assert len(result["posts"]) == 4
        assert result["product_name"] == product["name"]
        for post in result["posts"]:
            assert post["within_limit"], f"{product['slug']}/{post['channel']}"


# --------------------------------------------------------------- storefront


def test_home_lists_every_product(client):
    html = client.get("/").text
    assert client.get("/").status_code == 200
    for product in catalog.list_products():
        assert product["name"] in html
        assert product["slug"] in html


def test_every_product_has_a_landing_page(client):
    for product in catalog.list_products():
        response = client.get(f"/products/{product['slug']}")
        assert response.status_code == 200, product["slug"]
        html = response.text
        assert product["name"] in html
        # The Marketing AI's drafted copy appears on the page.
        assert "Campaign copy drafted by the Marketing AI" in html


def test_unknown_product_page_is_404(client):
    assert client.get("/products/nope").status_code == 404


def test_catalog_api(client):
    body = client.get("/api/catalog").json()
    assert body["count"] == 13
    assert len(body["products"]) == 13
    assert all("slug" in p and "price_month" in p for p in body["products"])


def test_app_store_page_lists_every_system(client):
    response = client.get("/app-store")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    html = response.text
    assert 'id="catalog"' in html
    for product in catalog.list_products():
        assert product["name"] in html


def test_product_pages_link_out_to_live_demos(client):
    html = client.get("/products/offsite-login-timekeeping-system").text
    assert "https://mjkulit03.github.io/offsite-employee-login/" in html
    assert "Open live demo" in html


def test_product_api_returns_marketing_and_sales(client):
    body = client.get("/api/products/grocery-sales-inventory-system").json()
    assert body["product"]["slug"] == "grocery-sales-inventory-system"
    assert len(body["marketing"]["posts"]) == 4
    assert len(body["sales"]["emails"]) == 2


# -------------------------------------------------------------------- leads


def test_inquiry_records_lead_and_drafts_outreach(client):
    response = client.post(
        "/api/products/office-supplies-inventory-system/inquiries",
        json={
            "product_slug": "office-supplies-inventory-system",
            "contact_name": "Sam",
            "email": "sam@example.com",
            "organisation": "Acme Offices",
            "seats": 5,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["lead_id"]
    assert body["estimated_value"] > 0
    assert len(body["outreach"]["emails"]) == 2
    assert len(store.list_leads()) == 1


def test_small_lead_does_not_escalate(client, monkeypatch):
    monkeypatch.setenv("LEAD_VALUE_THRESHOLD", "10000000")
    response = client.post(
        "/api/products/office-supplies-inventory-system/inquiries",
        json={"product_slug": "office-supplies-inventory-system",
              "contact_name": "Sam", "email": "sam@example.com", "seats": 1},
    )
    assert response.json()["escalated"] is False
    assert store.list_escalations("pending") == []


def test_high_value_lead_escalates(client):
    response = client.post(
        "/api/products/it-asset-management-system/inquiries",
        json={"product_slug": "it-asset-management-system",
              "contact_name": "Dana", "email": "dana@example.com", "seats": 200},
    )
    body = response.json()
    assert body["escalated"] is True
    pending = store.list_escalations("pending")
    assert len(pending) == 1
    assert pending[0]["kind"] == "high_value_lead"


def test_lead_escalation_summary_reads_sensibly_without_organisation():
    """Regression: an empty organisation produced 'Dana Reyes at  is worth ...'."""
    from notifications.config import get_settings
    from notifications.escalations import build_lead_escalation

    escalation = build_lead_escalation(
        {"contact_name": "Dana Reyes", "organisation": "", "estimated_value": 200000,
         "product_name": "Grocery System"},
        get_settings(),
    )
    summary = escalation.summary
    assert " at  " not in summary
    assert "Dana Reyes is worth" in summary


def test_lead_escalation_summary_includes_organisation_when_given():
    from notifications.config import get_settings
    from notifications.escalations import build_lead_escalation

    escalation = build_lead_escalation(
        {"contact_name": "Dana Reyes", "organisation": "Northwind", "estimated_value": 200000,
         "product_name": "Grocery System"},
        get_settings(),
    )
    assert "Dana Reyes at Northwind" in escalation.summary


# -------------------------------------------------------------- escalation


def test_sensitive_category_campaign_requires_approval(client):
    body = client.get("/api/products/clinic-inventory-system/campaign").json()
    assert body["campaign"]["escalation_id"]
    escalation = store.get_escalation(body["campaign"]["escalation_id"])
    assert escalation["kind"] == "campaign_approval"


def test_accounting_anomaly_escalates(client):
    response = client.post(
        "/api/accounting/report",
        json={"entries": [
            {"type": "income", "amount": 10000, "category": "Revenue"},
            {"type": "expense", "amount": 180000, "category": "Rent"},
        ]},
    )
    body = response.json()
    assert body["escalated"] is True
    escalation = store.get_escalation(body["escalation_id"])
    assert escalation["kind"] == "accounting_anomaly"
    assert escalation["severity"] == "critical"


def test_accounting_report_requires_entries(client):
    assert client.post("/api/accounting/report", json={"entries": []}).status_code == 400


# -------------------------------------------------------------------- auth


def test_control_api_fails_closed_without_accounts(monkeypatch):
    """No users at all -> 503, so a fresh deploy is never accidentally open."""
    assert users.list_users() == []
    monkeypatch.delenv("CONTROL_PANEL_PASSWORD", raising=False)
    c = TestClient(app)
    assert c.get("/api/control/overview").status_code == 503
    assert "disabled" in c.get("/api/control/overview").json()["detail"].lower()


def test_control_api_requires_authentication(client):
    assert client.get("/api/control/overview").status_code == 401
    assert client.get("/api/control/escalations").status_code == 401
    assert client.post("/api/worker/run").status_code == 401


def test_login_flow(monkeypatch):
    c = signed_in_client(monkeypatch)
    assert c.get("/api/control/overview").status_code == 200

    c.get("/control/logout", follow_redirects=False)
    assert c.get("/api/control/overview").status_code == 401


def test_wrong_password_does_not_authenticate(client):
    client.post(
        "/control/login",
        data={"username": "admin", "password": "not-the-password"},
        follow_redirects=False,
    )
    assert client.get("/api/control/overview").status_code == 401


def test_login_page_explains_disabled_panel(monkeypatch):
    monkeypatch.delenv("CONTROL_PANEL_PASSWORD", raising=False)
    html = TestClient(app).get("/control/login").text
    assert "Control panel disabled" in html


def test_short_password_is_rejected_by_config(monkeypatch):
    import auth

    monkeypatch.setenv("CONTROL_PANEL_PASSWORD", "abc")
    settings = notify_config.get_settings()
    assert settings.panel_enabled  # a value is set...
    problem = auth.panel_problem(settings)
    assert problem is None or "8 characters" in problem  # ...but it is too short


# ----------------------------------------------------------- notifications


def test_no_secret_appears_in_public_status(monkeypatch):
    monkeypatch.setenv("SMTP_PASSWORD", "hunter2-secret")
    monkeypatch.setenv("NOTIFY_WEBHOOK_TOKEN", "webhook-secret-value")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM", "alerts@example.com")
    monkeypatch.setenv("ALERT_EMAILS", "ops@example.com")
    monkeypatch.setenv("NOTIFY_WEBHOOK_URL", "https://hooks.example.com/abc")

    status = notify_config.get_settings().public_status()
    dumped = json.dumps(status)
    assert "hunter2-secret" not in dumped
    assert "webhook-secret-value" not in dumped
    assert "smtp.example.com" in dumped  # host is not a secret


def test_mask_hides_secret_but_keeps_recognisable_tail():
    settings = notify_config.NotificationSettings(smtp_password="supersecret")
    masked = settings.mask("supersecret")
    assert "supersecret" not in masked
    assert masked.endswith("et")


def test_notifier_is_inert_when_disabled(monkeypatch):
    monkeypatch.setenv("NOTIFY_ENABLED", "false")
    from notifications.notifier import Notifier

    results = Notifier(notify_config.get_settings()).send("subject", "body")
    assert len(results) == 1
    assert results[0].ok is False
    assert "disabled" in results[0].detail


def test_notifier_reports_unconfigured_email(monkeypatch):
    monkeypatch.setenv("NOTIFY_ENABLED", "true")
    monkeypatch.setenv("NOTIFY_CHANNELS", "email")
    for name in ("SMTP_HOST", "SMTP_FROM", "ALERT_EMAILS"):
        monkeypatch.delenv(name, raising=False)
    from notifications.notifier import Notifier

    results = Notifier(notify_config.get_settings()).send("subject", "body")
    assert results[0].ok is False
    # Email is requested but not usable, so it is not an active channel at all.
    assert "no notification channel is configured" in results[0].detail


def test_email_transport_reports_missing_smtp(monkeypatch):
    """The SMTP helper reports its own misconfiguration when called directly."""
    from notifications.notifier import _send_email

    settings = notify_config.NotificationSettings()
    result = _send_email(settings, "subject", "body")
    assert result.ok is False
    assert "SMTP not configured" in result.detail


# ------------------------------------------------------------------ worker


def test_worker_dry_run_sends_nothing(client):
    store.create_escalation(
        kind="high_value_lead", severity="high", title="T", summary="S"
    )
    summary = worker.run_once(dry_run=True)
    assert summary["dry_run"] is True
    assert summary["pending"] == 1
    assert summary["sent"] == 0
    assert store.list_escalations("pending")[0].get("notified_at") is None


def test_worker_does_not_double_notify(client):
    store.create_escalation(
        kind="high_value_lead", severity="high", title="T", summary="S"
    )
    first = worker.run_once()
    second = worker.run_once()
    assert first["pending"] == 1
    assert second["pending"] == 0, "already-notified escalations must not resend"


def test_worker_keeps_pending_when_a_channel_is_configured(monkeypatch):
    """A real channel that fails must retry, not silently drop the alert."""
    monkeypatch.setenv("NOTIFY_ENABLED", "true")
    monkeypatch.setenv("NOTIFY_CHANNELS", "email")
    monkeypatch.setenv("SMTP_HOST", "127.0.0.1")  # nothing listening
    monkeypatch.setenv("SMTP_PORT", "1")
    monkeypatch.setenv("SMTP_FROM", "a@example.com")
    monkeypatch.setenv("ALERT_EMAILS", "ops@example.com")
    monkeypatch.setenv("SMTP_USE_TLS", "false")

    store.create_escalation(
        kind="accounting_anomaly", severity="critical", title="T", summary="S"
    )
    summary = worker.run_once()
    assert summary["failed"] == 1
    assert summary["dropped"] == 0
    assert store.list_escalations("pending")[0].get("notified_at") is None


def test_worker_marks_handled_when_no_channel_exists(client):
    store.create_escalation(
        kind="high_value_lead", severity="high", title="T", summary="S"
    )
    summary = worker.run_once()
    assert summary["dropped"] == 1

    # It stays "pending" for a human decision -- only the notification state
    # changed -- but it must not be picked up and retried by the next run.
    item = store.list_escalations("pending")[0]
    assert item["notified_at"] is not None
    assert item["notification"]["dropped"] is True
    assert worker.run_once()["pending"] == 0


def test_worker_cli_runs_as_a_module(client):
    result = subprocess.run(
        [sys.executable, "-m", "notifications.worker", "--json"],
        capture_output=True, text=True, cwd=ROOT,
        env={**os.environ, "DATA_DIR": os.environ["DATA_DIR"]},
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert "pending" in payload and "channels" in payload


# --------------------------------------------------------------- traffic


def test_product_page_view_is_recorded(client):
    client.get("/products/hardware-inventory-system")
    events = store.list_events()
    assert any(e["kind"] == "pageview" and e["product_slug"] == "hardware-inventory-system" for e in events)


def test_referrer_is_grouped_by_host(client):
    client.get("/products/clinic-inventory-system", headers={"referer": "https://www.google.com/search?q=x"})
    client.get("/products/clinic-inventory-system", headers={"referer": "https://google.com/other"})
    assert traffic.normalise_referrer("https://www.google.com/search?q=x") == "google.com"
    summary = traffic.summary()
    assert summary["top_referrers"].get("google.com") == 2


def test_traffic_summary_aggregates_views_and_funnel(client):
    for _ in range(3):
        client.get("/products/grocery-sales-inventory-system")
    client.post(
        "/products/grocery-sales-inventory-system/inquiry",
        data={"contact_name": "Sam", "email": "s@e.com", "seats": "3"},
        follow_redirects=True,
    )
    summary = traffic.summary()
    assert summary["total_views"] >= 3
    assert summary["total_inquiries"] == 1
    assert summary["views_by_product"]["grocery-sales-inventory-system"] >= 3
    assert 0 < summary["conversion_pct"] <= 100
    assert summary["most_viewed_products"][0] == "grocery-sales-inventory-system"


def test_traffic_empty_state_is_safe():
    summary = traffic.summary()
    assert summary["total_views"] == 0
    assert summary["conversion_pct"] == 0.0
    assert summary["views_by_product"] == {}


def test_control_api_exposes_traffic(signed_in_client_pass):
    c = signed_in_client_pass
    c.get("/products/office-supplies-inventory-system")
    report = c.get("/api/control/traffic").json()
    assert report["total_views"] >= 1
    assert "daily_views" in report and "top_referrers" in report
    overview = c.get("/api/control/overview").json()
    assert overview["traffic"]["total_views"] >= 1
    assert c.get("/api/control/traffic?days=0").status_code == 400
    assert c.get("/api/control/traffic?days=999").status_code == 400


def test_traffic_requires_authentication(client):
    assert client.get("/api/control/traffic").status_code == 401


def test_control_overview_page_shows_traffic(signed_in_client_pass):
    signed_in_client_pass.get("/products/student-record-facial-recognition-system")
    html = signed_in_client_pass.get("/control/overview").text
    assert "Traffic analysis" in html
    assert "Interest by product" in html
    assert "View → inquiry" in html


def test_dotenv_is_loaded(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "# comment\n"
        "SMTP_HOST=smtp.example.com\n"
        "ALERT_EMAILS=a@example.com,b@example.com\n"
        'SMTP_PASSWORD="quoted secret"\n'
        "export EXPORTED_KEY=exported\n"
        "NO_EQUALS_SIGN\n"
        "\n",
        encoding="utf-8",
    )
    for key in ("SMTP_HOST", "ALERT_EMAILS", "SMTP_PASSWORD", "EXPORTED_KEY"):
        monkeypatch.delenv(key, raising=False)

    loaded = notify_config.load_dotenv(env)
    assert loaded == 4
    assert os.environ["SMTP_HOST"] == "smtp.example.com"
    assert os.environ["ALERT_EMAILS"] == "a@example.com,b@example.com"
    assert os.environ["SMTP_PASSWORD"] == "quoted secret"  # quotes stripped
    assert os.environ["EXPORTED_KEY"] == "exported"


def test_dotenv_never_overrides_real_environment(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("CONTROL_PANEL_PASSWORD=from-file\n", encoding="utf-8")
    monkeypatch.setenv("CONTROL_PANEL_PASSWORD", "from-shell")

    notify_config.load_dotenv(env)
    assert os.environ["CONTROL_PANEL_PASSWORD"] == "from-shell"

    notify_config.load_dotenv(env, override=True)
    assert os.environ["CONTROL_PANEL_PASSWORD"] == "from-file"


def test_missing_dotenv_is_not_an_error(tmp_path):
    assert notify_config.load_dotenv(tmp_path / "nope.env") == 0


# ------------------------------------------------------------ deploy files


def test_github_workflow_exists_and_is_valid_yaml():
    path = ROOT / ".github" / "workflows" / "ai_background_worker.yml"
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "schedule" in text and "cron" in text
    assert "notifications.worker" in text
    assert "workflow_dispatch" in text
    # Must reference secrets rather than inline values.
    assert "${{ secrets." in text
    assert re.search(r"^\s*-\s+cron:", text, re.M)


def test_ci_workflow_runs_the_tests():
    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "pytest" in text


def test_env_example_exists_and_has_no_real_secrets():
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    for key in (
        "CONTROL_PANEL_PASSWORD", "SESSION_SECRET", "NOTIFY_ENABLED",
        "SMTP_HOST", "SMTP_PASSWORD", "ALERT_EMAILS",
        "NOTIFY_WEBHOOK_URL", "NOTIFY_WEBHOOK_TOKEN",
        "LEAD_VALUE_THRESHOLD", "DATA_DIR",
        "BASE_CURRENCY", "FX_USD", "SEED_DEMO_USERS", "DEMO_USER_PASSWORD",
        "QUOTE_VAT_RATE", "QUOTE_MAINTENANCE_PCT",
    ):
        assert key in text, f"{key} missing from .env.example"

    # Every assignment must be empty or an explicitly allow-listed non-secret default.
    boolean_keys = {"NOTIFY_ENABLED", "SMTP_USE_TLS", "SEED_DEMO_USERS"}
    numeric_keys = {
        "SMTP_PORT", "LEAD_VALUE_THRESHOLD", "ACCOUNTING_ANOMALY_THRESHOLD",
        "QUOTE_VAT_RATE", "QUOTE_VALIDITY_DAYS", "QUOTE_DOWN_PAYMENT_PCT",
        "QUOTE_ON_IMPLEMENTATION_PCT", "QUOTE_MAINTENANCE_PCT",
        "QUOTE_MARGIN_FLOOR_PCT", "QUOTE_DISCOUNT_APPROVAL_PCT",
    }
    free_text_defaults = {
        "NOTIFY_CHANNELS", "NOTIFY_WEBHOOK_PROVIDER", "DATA_DIR",
        "CONTROL_PANEL_ADMIN_USER",  # default username, not a secret
        "BASE_CURRENCY",             # currency code, not a secret
    }
    for line in text.splitlines():
        match = re.match(r"^([A-Z_]+)=(.*)$", line.strip())
        if not match:
            continue
        name, value = match.groups()
        if name.startswith("FX_"):
            assert value.replace(".", "").isdigit(), f"{name} must be a rate"
        elif name in boolean_keys:
            assert value in {"true", "false"}, name
        elif name in numeric_keys:
            assert value.replace(".", "").isdigit(), name
        elif name in free_text_defaults:
            continue
        else:
            assert value == "", f"{name} must ship empty, found {value!r}"


def test_gitignore_protects_secrets_and_runtime_data():
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in text
    assert "!.env.example" in text
    assert "var/" in text


def test_no_secrets_hardcoded_in_source():
    """Scan the shipped Python for anything that looks like a credential."""
    suspicious = re.compile(
        r"(?i)(password|secret|api[_-]?key|token)\s*=\s*['\"][^'\"]{8,}['\"]"
    )
    allowed = {"CONTROL_PANEL_PASSWORD", "SESSION_SECRET"}
    offenders = []
    for path in ROOT.rglob("*.py"):
        parts = set(path.parts)
        if parts & {".venv", "venv", "__pycache__", "tests"}:
            continue  # test fixtures use throwaway literals by design
        for line in path.read_text(encoding="utf-8").splitlines():
            if any(name in line for name in allowed):
                continue
            if suspicious.search(line):
                offenders.append(f"{path.name}: {line.strip()}")
    assert not offenders, offenders


def test_templates_exist_and_autoescape_product_copy():
    for name in ("base.html", "index.html", "product.html", "login.html", "overview.html", "campaign.html"):
        assert (ROOT / "templates" / name).exists(), name