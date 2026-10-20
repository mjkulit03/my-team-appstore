"""Tests for quotations, payment terms and the Marketing -> Sales -> Accounting pipeline."""

from __future__ import annotations

import pytest
from decimal import Decimal
from fastapi.testclient import TestClient

import catalog
import quotation as quote_lib
import store
import users
from main import app
from notifications.config import NotificationSettings
from orchestrator import run_quotation_pipeline

PRODUCT = catalog.find_product("clinic-inventory-system")


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    for key in ("QUOTE_VAT_RATE", "QUOTE_VALIDITY_DAYS", "QUOTE_DOWN_PAYMENT_PCT",
                "QUOTE_ON_IMPLEMENTATION_PCT", "QUOTE_MAINTENANCE_PCT",
                "QUOTE_MARGIN_FLOOR_PCT", "QUOTE_DISCOUNT_APPROVAL_PCT",
                "BASE_CURRENCY", "FX_USD"):
        monkeypatch.delenv(key, raising=False)
    store.reset_for_tests()
    yield
    store.reset_for_tests()


def customer(email: str = "ana@clinic.ph") -> dict:
    return {"name": "Ana Reyes", "email": email, "organisation": "Reyes Dental"}


def offline_settings() -> NotificationSettings:
    """SMTP configured but unreachable, so delivery attempts are observable."""
    return NotificationSettings(
        smtp_host="127.0.0.1",
        smtp_port=1,
        smtp_from="sales@example.com",
        alert_emails=["ops@example.com"],
        smtp_use_tls=False,
        enabled=True,
        channels=["email"],
    )


# ------------------------------------------------------------ line items


def test_quotation_numbers_lines_correctly():
    quote = quote_lib.build_quotation(PRODUCT, customer(), seats=20, term_months=12)
    subscription = quote_lib._q(PRODUCT["price_month"] * 20 * 12)
    assert len(quote.lines) == 2
    assert quote.lines[0].amount == subscription
    assert quote.lines[1].amount == Decimal(str(PRODUCT["price_setup"]))
    assert quote.subtotal == subscription + Decimal(str(PRODUCT["price_setup"]))


def test_support_line_is_optional():
    without = quote_lib.build_quotation(PRODUCT, customer(), seats=5)
    with_support = quote_lib.build_quotation(PRODUCT, customer(), seats=5, support=True)
    assert len(without.lines) == 2
    assert len(with_support.lines) == 3
    assert with_support.total > without.total


def test_discount_reduces_the_contract():
    plain = quote_lib.build_quotation(PRODUCT, customer(), seats=10)
    discounted = quote_lib.build_quotation(PRODUCT, customer(), seats=10, discount_pct=10)
    assert discounted.discount_amount == quote_lib._q(plain.subtotal * Decimal("0.10"))
    assert discounted.contract_value == plain.contract_value - discounted.discount_amount


def test_invalid_discount_is_rejected():
    for bad in (-1, 101):
        with pytest.raises(ValueError):
            quote_lib.build_quotation(PRODUCT, customer(), discount_pct=bad)


# ------------------------------------------------------------------ VAT


def test_vat_is_extracted_from_an_inclusive_total():
    """Catalog prices are VAT-inclusive, so VAT is a component of the total."""
    quote = quote_lib.build_quotation(PRODUCT, customer(), seats=10)
    expected = quote_lib._q(quote.net - (quote.net / Decimal("1.12")))
    assert quote.vat == expected
    # The customer never pays more than the quoted total.
    assert quote.total == quote.net
    assert quote.total + Decimal("0.01") > quote.total


def test_vat_rate_is_configurable(monkeypatch):
    monkeypatch.setenv("QUOTE_VAT_RATE", "0.20")
    quote = quote_lib.build_quotation(PRODUCT, customer(), seats=10)
    assert quote.vat_rate == Decimal("0.20")
    expected = quote_lib._q(quote.net - (quote.net / Decimal("1.20")))
    assert quote.vat == expected


def test_bad_vat_rate_falls_back(monkeypatch):
    monkeypatch.setenv("QUOTE_VAT_RATE", "not-a-number")
    assert quote_lib.vat_rate() == quote_lib.DEFAULT_VAT_RATE


def test_zero_vat_is_allowed(monkeypatch):
    monkeypatch.setenv("QUOTE_VAT_RATE", "0")
    quote = quote_lib.build_quotation(PRODUCT, customer(), seats=10)
    assert quote.vat == Decimal("0.00")


# -------------------------------------------------------- payment terms


def test_payment_terms_are_50_50_plus_30_maintenance():
    """Offline/on-premise terms: 50% on approval, 50% on go-live, 30% retainer."""
    quote = quote_lib.build_quotation(PRODUCT, customer(), seats=20, term_months=12)
    schedule = quote.payment_schedule
    assert len(schedule) == 3

    approval, go_live, maintenance = schedule
    assert approval["trigger"] == "On approval"
    assert go_live["trigger"] == "On go-live"
    assert maintenance["trigger"] == "Annually from go-live"

    assert approval["amount"] == go_live["amount"] == quote_lib._q(quote.contract_value / 2)
    assert maintenance["amount"] == quote_lib._q(quote.contract_value * Decimal("0.30"))
    assert quote.maintenance == maintenance["amount"]


def test_two_instalments_exactly_reconstruct_the_contract():
    quote = quote_lib.build_quotation(PRODUCT, customer(), seats=7, term_months=24)
    instalments = sum(
        Decimal(str(i["amount"])) for i in quote.payment_schedule if i["trigger"] != "Annually from go-live"
    )
    assert instalments == quote.contract_value


def test_year_one_total_is_contract_plus_maintenance():
    quote = quote_lib.build_quotation(PRODUCT, customer(), seats=10)
    assert quote.year_one_total == quote.contract_value + quote.maintenance
    assert quote.maintenance == quote_lib._q(quote.contract_value * Decimal("0.30"))


def test_payment_terms_are_configurable(monkeypatch):
    monkeypatch.setenv("QUOTE_DOWN_PAYMENT_PCT", "30")
    monkeypatch.setenv("QUOTE_ON_IMPLEMENTATION_PCT", "70")
    monkeypatch.setenv("QUOTE_MAINTENANCE_PCT", "20")
    quote = quote_lib.build_quotation(PRODUCT, customer(), seats=10)
    approval, go_live, maintenance = quote.payment_schedule
    assert approval["amount"] == quote_lib._q(quote.contract_value * Decimal("0.30"))
    assert approval["amount"] + go_live["amount"] == quote.contract_value
    assert maintenance["amount"] == quote_lib._q(quote.contract_value * Decimal("0.20"))


def test_percentages_never_render_in_scientific_notation():
    """Regression: Decimal('30').normalize() is 3E+1 and must not reach a quote."""
    quote = quote_lib.build_quotation(PRODUCT, customer(), seats=10)
    text = quote_lib.render_text(quote)
    assert "3E+1" not in text
    assert "30%" in text
    assert "12%" in text
    assert quote_lib.pct(Decimal("30")) == "30"
    assert quote_lib.pct(Decimal("1.12") * 100 - 100) == "12"


def test_reference_and_validity():
    quote = quote_lib.build_quotation(PRODUCT, customer(), seats=1)
    assert quote.reference.startswith("QT-")
    assert len(quote.reference.split("-")) == 3
    assert quote.valid_until > quote.created_at[:10]


def test_gross_margin_uses_year_one_revenue():
    quote = quote_lib.build_quotation(PRODUCT, customer(), seats=10)
    margin = quote_lib.gross_margin(quote, PRODUCT)
    assert 0 < margin < 100
    assert margin > Decimal("50")  # healthy software margin


# ----------------------------------------------------------- pipeline


def test_pipeline_runs_all_four_agents():
    result = run_quotation_pipeline(
        PRODUCT, customer(), seats=10, send_email=False, settings=offline_settings()
    )
    assert result["status"] == "approved_not_sent"
    agents = [s["agent"] for s in result["transcript"]]
    assert agents == ["Marketing AI", "Sales AI", "Accounting AI", "Delivery"]
    assert result["quotation"]["reference"].startswith("QT-")


def test_pipeline_records_the_quotation():
    result = run_quotation_pipeline(
        PRODUCT, customer(), seats=10, send_email=False, settings=offline_settings()
    )
    stored = store.get_quotation(result["quotation_id"])
    assert stored["product_slug"] == PRODUCT["slug"]
    assert stored["status"] == "approved_not_sent"
    assert stored["quotation"]["year_one_total"] > 0
    assert stored["pricing_check"]["approved"] is True


def test_accounting_holds_a_heavy_discount():
    result = run_quotation_pipeline(
        PRODUCT, customer(), seats=10, discount_pct=40,
        send_email=False, settings=offline_settings(),
    )
    assert result["status"] == "needs_approval"
    assert result["email"]["sent"] is False
    pending = store.list_escalations("pending")
    assert any(e["kind"] == "pricing_approval" for e in pending)


def test_discount_within_policy_is_approved():
    result = run_quotation_pipeline(
        PRODUCT, customer(), seats=10, discount_pct=10,
        send_email=False, settings=offline_settings(),
    )
    assert result["status"] == "approved_not_sent"
    assert store.list_escalations("pending") == []


def test_low_margin_holds_the_quote(monkeypatch):
    monkeypatch.setenv("QUOTE_MARGIN_FLOOR_PCT", "99")
    result = run_quotation_pipeline(
        PRODUCT, customer(), seats=10, send_email=False, settings=offline_settings()
    )
    assert result["status"] == "needs_approval"
    assert any("margin" in b for b in result["transcript"][2]["data"]["breaches"])


def test_pipeline_requires_name_and_email():
    with pytest.raises(ValueError):
        run_quotation_pipeline(PRODUCT, {"name": "", "email": "a@b.co"})
    with pytest.raises(ValueError):
        run_quotation_pipeline(PRODUCT, {"name": "Ana", "email": ""})


# ------------------------------------------------------------- delivery


def test_invalid_email_is_not_sent():
    result = run_quotation_pipeline(
        PRODUCT, customer(email="not-an-email"), seats=5,
        settings=offline_settings(),
    )
    assert result["status"] == "no_email"
    assert result["email"]["sent"] is False


def test_send_attempted_when_smtp_configured():
    result = run_quotation_pipeline(
        PRODUCT, customer(), seats=5, settings=offline_settings()
    )
    # Nothing is listening on 127.0.0.1:1, so delivery must fail cleanly.
    assert result["status"] == "failed"
    assert result["email"]["sent"] is False
    assert "Error" in result["email"]["detail"] or "refused" in result["email"]["detail"].lower()


def test_no_email_sent_when_smtp_unconfigured():
    settings = NotificationSettings()  # nothing configured
    result = run_quotation_pipeline(PRODUCT, customer(), seats=5, settings=settings)
    assert result["status"] == "failed"
    assert "not configured" in result["email"]["detail"]


def test_send_email_to_rejects_header_injection():
    from notifications.notifier import send_email_to, valid_email

    assert valid_email("ok@example.com")
    assert not valid_email("bad@x")
    assert not valid_email("a@b.com, c@d.com")  # no extra recipients
    assert not valid_email("a@b.com\r\nBcc: attacker@evil.com")

    result = send_email_to(
        NotificationSettings(smtp_host="127.0.0.1", smtp_port=1, smtp_from="s@x.com"),
        ["attacker@evil.com\r\nBcc: victim@x.com"],
        "subject\r\nBcc: someone@else.com",
        "body",
    )
    assert result.ok is False
    assert "no valid recipient" in result.detail


# ---------------------------------------------------------------- API


def test_quotation_api_endpoint():
    c = TestClient(app)
    response = c.post(
        "/api/quotations",
        json={"product_slug": "grocery-sales-inventory-system", "name": "Ana Reyes",
              "email": "ana@example.com", "seats": 12, "send_email": False},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approved_not_sent"
    assert body["quotation"]["payment_schedule"][0]["amount"] > 0
    assert len(body["transcript"]) == 4


def test_quotation_api_by_product_slug():
    c = TestClient(app)
    response = c.post(
        "/api/products/hardware-inventory-system/quotation",
        json={"name": "Ana Reyes", "email": "ana@example.com", "seats": 3, "send_email": False},
    )
    assert response.status_code == 200
    assert response.json()["quotation"]["product"]["slug"] == "hardware-inventory-system"


def test_quotation_api_rejects_unknown_product():
    assert TestClient(app).post(
        "/api/quotations",
        json={"product_slug": "nope", "name": "Ana Reyes", "email": "a@b.co"},
    ).status_code == 404


def test_quotation_api_validates_seats():
    assert TestClient(app).post(
        "/api/quotations",
        json={"product_slug": "grocery-sales-inventory-system", "name": "A",
              "email": "a@b.co", "seats": 0},
    ).status_code == 422


def test_quotation_page_renders_payment_terms():
    html = TestClient(app).get("/products/clinic-inventory-system").text
    assert "50% on approval" in html
    assert "after implementation completes" in html
    assert "annual maintenance retainer" in html


def test_quotation_api_requires_product_slug():
    response = TestClient(app).post("/api/quotations", json={"name": "Ana Reyes", "email": "a@b.co"})
    assert response.status_code == 400


def test_quotation_page_flows_through():
    c = TestClient(app)
    response = c.post(
        "/products/clinic-inventory-system/quotation",
        data={"name": "Ana Reyes", "email": "ana@clinic.ph", "organisation": "Reyes Dental",
              "seats": "10", "term_months": "12", "send_email": "false"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "First-year total" in response.text
    assert "On approval" in response.text
    assert "On go-live" in response.text
    assert "Annual maintenance" in response.text


def test_control_api_lists_quotations(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "s")
    users.create_user("boss", "boss-password-1", "admin")
    c = TestClient(app)
    c.post("/control/login", data={"username": "boss", "password": "boss-password-1"})
    run_quotation_pipeline(PRODUCT, customer(), seats=4, send_email=False, settings=offline_settings())
    body = c.get("/api/control/quotations").json()
    assert body["count"] == 1
    assert body["quotations"][0]["status"] == "approved_not_sent"
    assert body["total_value"] > 0