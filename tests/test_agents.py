"""Tests for the three simulated agents, both as functions and over HTTP."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agents import run_accounting_agent, run_marketing_agent, run_sales_agent
from agents import textkit as tk
from main import app

client = TestClient(app)


# --------------------------------------------------------------------------
# textkit
# --------------------------------------------------------------------------

def test_top_keywords_drops_stopwords_and_is_deterministic():
    text = "The invoice system and the invoice system process invoices for a team."
    first = tk.top_keywords(text, limit=3)
    assert first == tk.top_keywords(text, limit=3)
    assert "invoice" in first
    assert "the" not in first


def test_top_keywords_excludes_generic_verbs_and_adverbs():
    keywords = tk.top_keywords(DESCRIPTION, limit=10)
    assert "automates" not in keywords
    assert "directly" not in keywords
    assert "invoice" in keywords
    assert all(not k.endswith("ing") for k in keywords)


def test_fit_truncates_on_word_boundary():
    out = tk.fit("alpha beta gamma delta", 12)
    assert out.endswith("\u2026")
    assert len(out) <= 12


def test_fit_with_tail_keeps_tail_intact():
    body = "word " * 200
    out = tk.fit_with_tail(body.strip(), "#one #two", 60)
    assert out.endswith("#one #two")
    assert len(out) <= 60


# --------------------------------------------------------------------------
# Marketing Agent
# --------------------------------------------------------------------------

DESCRIPTION = (
    "A SaaS platform that automates invoice reconciliation for small e-commerce "
    "merchants and syncs receipts directly into accounting software"
)


def test_marketing_returns_a_post_per_channel():
    out = run_marketing_agent(product_description=DESCRIPTION)
    assert {p["channel"] for p in out["posts"]} == {"x", "linkedin", "instagram", "facebook"}
    assert out["detected_category"] == "saas"
    assert out["strategy"]


def test_marketing_respects_character_limits():
    out = run_marketing_agent(product_description=DESCRIPTION)
    for post in out["posts"]:
        assert post["char_count"] <= post["char_limit"], post["channel"]
        assert post["within_limit"]


def test_marketing_truncates_long_product_names_on_x():
    out = run_marketing_agent(
        product_description=DESCRIPTION,
        product_name="An Extremely Long Product Name That Will Not Fit On One Hundred Eighty Characters " * 3,
    )
    x_post = next(p for p in out["posts"] if p["channel"] == "x")
    assert x_post["char_count"] <= 280
    assert x_post["truncated"] is True


def test_marketing_keeps_hashtags_after_truncation():
    out = run_marketing_agent(
        product_description=DESCRIPTION,
        product_name="An Extremely Long Product Name " * 20,
    )
    x_post = next(p for p in out["posts"] if p["channel"] == "x")
    assert x_post["hashtags"]
    for tag in x_post["hashtags"]:
        assert tag in x_post["post"]


def test_marketing_honours_channel_subset():
    out = run_marketing_agent(product_description=DESCRIPTION, channels=["linkedin"])
    assert [p["channel"] for p in out["posts"]] == ["linkedin"]


def test_marketing_copy_contains_no_generic_verbs():
    out = run_marketing_agent(product_description=DESCRIPTION)
    blob = " ".join(p["post"].lower() for p in out["posts"])
    # Regression: "covers accounting, automates, commerce" once shipped as output.
    assert "automates," not in blob
    assert "directly" not in blob


def test_marketing_infers_a_readable_product_name():
    out = run_marketing_agent(product_description=DESCRIPTION)
    name = out["product_name"]
    # Regression: this used to return the run-on phrase
    # "Saas Platform Automates Invoice Reconciliation Small E Commerce".
    assert len(name.split()) <= 3, name
    assert "saas" not in name.lower()
    assert "platform" not in name.lower()
    assert "automates" not in name.lower()
    assert "small" not in name.lower()
    assert name == "Invoice Reconciliation Commerce", name


def test_marketing_falls_back_when_description_has_no_distinctive_words():
    out = run_marketing_agent(product_description="It is a software platform that helps a lot.")
    assert out["product_name"] == "Your Product"


def test_optional_schema_fields_default_to_none():
    """Regression: a stray trailing comma made `brand` default to a FieldInfo tuple."""
    from schemas import MarketingRequest

    request = MarketingRequest(product_description=DESCRIPTION)
    assert request.brand is None
    assert request.product_name is None
    assert not isinstance(request.brand, tuple)


def test_marketing_endpoint_never_leaks_field_repr():
    client = TestClient(app)
    body = client.post(
        "/api/agents/marketing",
        json={"product_description": DESCRIPTION, "brand": "Ledgerly Inc"},
    ).json()
    blob = " ".join(s["point"] for s in body["strategy"])
    assert "Ledgerly Inc" in blob
    assert "FieldInfo" not in blob


def test_marketing_omits_brand_point_when_no_brand():
    out = run_marketing_agent(product_description=DESCRIPTION)
    assert all("FieldInfo" not in s["point"] for s in out["strategy"])
    assert not any("brand assets" in s["point"] for s in out["strategy"])


def test_marketing_uses_product_name_override():
    out = run_marketing_agent(product_description=DESCRIPTION, product_name="Ledgerly")
    assert out["product_name"] == "Ledgerly"


def test_marketing_rejects_bad_input():
    with pytest.raises(ValueError):
        run_marketing_agent(product_description="")
    with pytest.raises(ValueError):
        run_marketing_agent(product_description=DESCRIPTION, tone="sarcastic")
    with pytest.raises(ValueError):
        run_marketing_agent(product_description=DESCRIPTION, channels=["tiktok"])


# --------------------------------------------------------------------------
# Sales Agent
# --------------------------------------------------------------------------

CUSTOMER = "small dental clinic owners"


def test_sales_returns_requested_variant_count():
    out = run_sales_agent(target_customer_type=CUSTOMER, variants=4)
    assert len(out["emails"]) == 4
    assert {e["variant"] for e in out["emails"]} == {"direct", "value_first", "question", "social_proof"}


def test_sales_emails_stay_within_length_budget():
    out = run_sales_agent(target_customer_type=CUSTOMER)
    for email in out["emails"]:
        assert email["word_count"] <= 150, email["variant"]
        assert email["within_length_budget"]
        assert email["subject_lines"]


@pytest.mark.parametrize(
    "audience,expected",
    [
        ("small dental clinic owners", "Owner"),
        ("ecommerce teams", "Team"),
        ("SaaS developers", "Developer"),
        ("beekeepers", "there"),
    ],
)
def test_sales_greeting_uses_head_noun(audience, expected):
    # Regression: the salutation used to be the first word ("Hi Small,").
    out = run_sales_agent(target_customer_type=audience)
    assert out["greeting_name"] == expected
    assert all(f"Hi {expected}," in e["body"] for e in out["emails"])


def test_sales_subject_lines_are_bounded():
    out = run_sales_agent(target_customer_type="owners of mid-sized specialty dental practices")
    for email in out["emails"]:
        for subject in email["subject_lines"]:
            assert len(subject) <= 60, subject


def test_sales_pain_point_is_a_noun_phrase():
    # Regression: gerund phrasing produced "cut hours on spending admin hours on ...".
    out = run_sales_agent(target_customer_type=CUSTOMER)
    assert not out["assumed_pain_point"].startswith("spending")
    assert all("on spending" not in e["body"] for e in out["emails"])


def test_sales_detects_industry_and_pain():
    out = run_sales_agent(target_customer_type=CUSTOMER)
    assert out["detected_industry"] == "healthcare"
    assert out["assumed_pain_point"]


def test_sales_falls_back_for_unknown_industry():
    out = run_sales_agent(target_customer_type="beekeepers")
    assert out["detected_industry"] == "general business"


def test_sales_provides_three_follow_ups():
    out = run_sales_agent(target_customer_type=CUSTOMER)
    assert [f["day"] for f in out["follow_up_sequence"]] == [3, 7, 14]


def test_sales_uses_offer_in_every_email():
    out = run_sales_agent(target_customer_type=CUSTOMER, offer="Free 30-day pilot.")
    assert all("Free 30-day pilot." in e["body"] for e in out["emails"])


def test_sales_rejects_bad_input():
    with pytest.raises(ValueError):
        run_sales_agent(target_customer_type="   ")
    with pytest.raises(ValueError):
        run_sales_agent(target_customer_type=CUSTOMER, tone="aggressive")
    with pytest.raises(ValueError):
        run_sales_agent(target_customer_type=CUSTOMER, variants=9)
    with pytest.raises(ValueError):
        run_sales_agent(target_customer_type=CUSTOMER, variants=True)


# --------------------------------------------------------------------------
# Accounting Agent
# --------------------------------------------------------------------------

ENTRIES = [
    {"type": "income", "amount": 1000.00, "category": "Subscription revenue", "date": "2026-03-01"},
    {"type": "income", "amount": 500.00, "category": "Services", "date": "2026-03-15"},
    {"type": "expense", "amount": 600.00, "category": "Payroll", "date": "2026-03-05"},
]


def test_accounting_computes_totals_correctly():
    out = run_accounting_agent(entries=ENTRIES)
    totals = out["totals"]
    assert totals["total_income"] == 1500.00
    assert totals["total_expenses"] == 600.00
    assert totals["net"] == 900.00
    assert totals["closing_balance"] == 900.00
    assert totals["profit_margin_pct"] == 60.0
    # Payroll is 100% of spending here, so the concentration alert correctly fires.
    assert out["status"] == "needs_attention"
    assert any(a["code"] == "expense_concentration" for a in out["alerts"])


def test_accounting_reports_healthy_for_diversified_spend():
    out = run_accounting_agent(
        entries=[
            {"type": "income", "amount": 5000, "category": "Revenue"},
            {"type": "expense", "amount": 350, "category": "Payroll"},
            {"type": "expense", "amount": 300, "category": "Rent"},
            {"type": "expense", "amount": 250, "category": "Software"},
            {"type": "expense", "amount": 100, "category": "Travel"},
        ]
    )
    assert out["status"] == "healthy"
    assert out["alerts"][0]["code"] == "healthy"


def test_accounting_includes_opening_balance():
    out = run_accounting_agent(entries=ENTRIES, opening_balance=250.00)
    assert out["totals"]["closing_balance"] == 1150.00


def test_accounting_category_shares_sum_to_100():
    out = run_accounting_agent(entries=ENTRIES)
    total_share = sum(row["share_pct"] for row in out["expenses_by_category"])
    assert round(total_share, 2) == 100.00


def test_accounting_money_survives_float_error():
    out = run_accounting_agent(
        entries=[
            {"type": "income", "amount": 0.10, "category": "A"},
            {"type": "income", "amount": 0.20, "category": "A"},
        ]
    )
    # 0.1 + 0.2 == 0.30000000000000004 in float; Decimal keeps it clean.
    assert out["totals"]["total_income"] == 0.30


def test_accounting_rounds_to_cents():
    out = run_accounting_agent(entries=[{"type": "income", "amount": 10.005, "category": "A"}])
    assert out["totals"]["total_income"] == 10.01


def test_accounting_flags_net_loss():
    out = run_accounting_agent(
        entries=[
            {"type": "income", "amount": 100, "category": "Revenue"},
            {"type": "expense", "amount": 400, "category": "Rent"},
        ]
    )
    assert out["totals"]["net"] == -300.00
    assert out["status"] == "critical"
    assert any(a["code"] == "net_loss" for a in out["alerts"])


def test_accounting_flags_expense_concentration():
    out = run_accounting_agent(
        entries=[
            {"type": "income", "amount": 1000, "category": "Revenue"},
            {"type": "expense", "amount": 900, "category": "Rent"},
            {"type": "expense", "amount": 50, "category": "Supplies"},
        ]
    )
    assert any(a["code"] == "expense_concentration" for a in out["alerts"])


def test_accounting_flags_thin_margin():
    out = run_accounting_agent(
        entries=[
            {"type": "income", "amount": 1000, "category": "Revenue"},
            {"type": "expense", "amount": 950, "category": "Costs"},
        ]
    )
    assert any(a["code"] == "thin_margin" for a in out["alerts"])


def test_accounting_flags_negative_opening_balance():
    out = run_accounting_agent(entries=ENTRIES, opening_balance=-100.0)
    assert any(a["code"] == "negative_opening_balance" for a in out["alerts"])


def test_accounting_monthly_totals():
    out = run_accounting_agent(entries=ENTRIES)
    assert out["monthly_totals"]["2026-03"]["income"] == 1500.00
    assert out["monthly_totals"]["2026-03"]["net"] == 900.00


def test_accounting_monthly_omitted_when_undated():
    out = run_accounting_agent(entries=[{"type": "income", "amount": 5, "category": "A"}])
    assert out["monthly_totals"] is None


def test_accounting_top_expenses_sorted():
    entries = [
        {"type": "expense", "amount": 10, "category": "Small"},
        {"type": "expense", "amount": 900, "category": "Big"},
        {"type": "expense", "amount": 50, "category": "Medium"},
    ]
    out = run_accounting_agent(entries=entries, top_n=2)
    assert [e["amount"] for e in out["top_expenses"]] == [900.0, 50.0]


def test_accounting_normalises_category_casing():
    out = run_accounting_agent(entries=[{"type": "income", "amount": 5, "category": "sales revenue"}])
    assert out["income_by_category"][0]["category"] == "Sales Revenue"


def test_accounting_rejects_bad_input():
    with pytest.raises(ValueError):
        run_accounting_agent(entries=[])
    with pytest.raises(ValueError):
        run_accounting_agent(entries=[{"type": "income", "amount": -50, "category": "A"}])
    with pytest.raises(ValueError):
        run_accounting_agent(entries=[{"type": "refund", "amount": 10, "category": "A"}])
    with pytest.raises(ValueError):
        run_accounting_agent(entries=[{"type": "income", "amount": 10}])
    with pytest.raises(ValueError):
        run_accounting_agent(entries=[{"type": "income", "amount": 10, "category": "A", "date": "03/01/2026"}])
    with pytest.raises(ValueError):
        run_accounting_agent(entries=[{"type": "income", "amount": "abc", "category": "A"}])
    with pytest.raises(ValueError):
        run_accounting_agent(entries="not a list")


# --------------------------------------------------------------------------
# HTTP endpoints
# --------------------------------------------------------------------------

def test_health_and_agent_listing():
    assert client.get("/health").json()["status"] == "ok"
    agents = client.get("/agents").json()["agents"]
    assert {a["id"] for a in agents} == {"marketing", "sales", "accounting"}


def test_marketing_endpoint():
    resp = client.post("/api/agents/marketing", json={"product_description": DESCRIPTION, "brand": "Ledgerly"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["agent"] == "marketing"
    assert len(body["posts"]) == 4
    assert all(p["char_count"] <= p["char_limit"] for p in body["posts"])
    assert any("Ledgerly" in s["point"] for s in body["strategy"])


def test_sales_endpoint():
    resp = client.post("/api/agents/sales", json={"target_customer_type": CUSTOMER, "variants": 2})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["emails"]) == 2
    assert body["detected_industry"] == "healthcare"


def test_accounting_endpoint():
    resp = client.post(
        "/api/agents/accounting",
        json={"entries": ENTRIES, "opening_balance": 100.0, "currency": "usd"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["totals"]["closing_balance"] == 1000.00
    assert body["currency"] == "USD"


def test_endpoints_return_422_on_schema_violations():
    assert client.post("/api/agents/marketing", json={"product_description": "short"}).status_code == 422
    assert client.post("/api/agents/marketing", json={}).status_code == 422
    assert client.post("/api/agents/sales", json={"target_customer_type": "ab"}).status_code == 422
    assert client.post("/api/agents/sales", json={"target_customer_type": ""}).status_code == 422
    assert client.post("/api/agents/sales", json={"target_customer_type": "a b c", "variants": 99}).status_code == 422
    assert client.post("/api/agents/accounting", json={"entries": []}).status_code == 422


def test_accounting_endpoint_returns_400_for_business_rule_violation():
    # -5 satisfies the pydantic schema (no gt=0), so the failure comes from the
    # agent's own validation and must surface as a 400, not a 500.
    resp = client.post(
        "/api/agents/accounting",
        json={"entries": [{"type": "expense", "amount": -5, "category": "Rent"}]},
    )
    assert resp.status_code == 400
    assert "greater than zero" in resp.json()["detail"]


def test_malformed_date_returns_400_not_500():
    resp = client.post(
        "/api/agents/accounting",
        json={"entries": [{"type": "income", "amount": 10, "category": "A", "date": "03/01/2026"}]},
    )
    assert resp.status_code == 400
    assert "ISO" in resp.json()["detail"]


def test_openapi_doc_is_served():
    assert client.get("/openapi.json").status_code == 200