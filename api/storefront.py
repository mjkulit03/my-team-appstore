"""Public storefront API: catalog, product pages and lead capture.

No authentication: this is the public face of the storefront. It reads the
catalog, asks the AI employees to draft copy, and records inquiries.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import catalog
import store
from agents import run_accounting_agent, run_marketing_agent, run_sales_agent
from notifications.config import get_settings
from notifications.escalations import build_campaign_escalation, build_lead_escalation
from orchestrator import run_quotation_pipeline

router = APIRouter(tags=["storefront"])


class Inquiry(BaseModel):
    product_slug: str = Field(..., min_length=2, description="Which product the inquiry is about.")
    contact_name: str = Field(..., min_length=2)
    email: str = Field(..., min_length=5)
    organisation: str = Field(default="", max_length=120)
    message: str = Field(default="", max_length=2000)
    seats: int = Field(default=1, ge=1, le=100000, description="Estimated seats, used for lead scoring.")


def _require_product(slug: str) -> dict:
    product = catalog.find_product(slug)
    if product is None:
        raise HTTPException(status_code=404, detail=f"No product with slug {slug!r}")
    return product


@router.get("/api/catalog")
def list_catalog() -> dict:
    """All products, as card-ready summaries."""
    products = catalog.list_products()
    return {
        "count": len(products),
        "categories": catalog.list_categories(),
        "products": [
            {
                "slug": p["slug"],
                "name": p["name"],
                "tagline": p["tagline"],
                "category": p["category"],
                "icon": p["icon"],
                "price_month": p["price_month"],
                "price_setup": p["price_setup"],
                "feature_count": len(p["features"]),
            }
            for p in products
        ],
    }


@router.get("/api/products/{slug}")
def get_product(slug: str) -> dict:
    """One product, with AI-drafted marketing and sales copy."""
    product = _require_product(slug)

    marketing = run_marketing_agent(
        product_description=product["description"],
        product_name=product["name"],
        tone="confident",
    )
    sales = run_sales_agent(
        target_customer_type=product["audience"],
        product_name=product["name"],
        offer=(
            f"Start a 30-day trial of {product['name']} for your team, "
            f"with the {product['price_setup']} setup fee waived."
        ),
        variants=2,
    )

    return {
        "product": product,
        "marketing": marketing,
        "sales": sales,
    }


@router.get("/api/products/{slug}/campaign", summary="Draft a marketing campaign")
def draft_campaign(slug: str, tone: str = "confident") -> dict:
    """Have the Marketing AI draft a campaign; queue it for human approval.

    This is the 'approving a marketing post' escalation path.
    """
    product = _require_product(slug)
    settings = get_settings()

    campaign = run_marketing_agent(
        product_description=product["description"],
        product_name=product["name"],
        brand=product["name"],
        tone=tone,
    )
    record = store.save_campaign(product["slug"], campaign)

    escalation = build_campaign_escalation(product, campaign, settings)
    if escalation:
        queued = store.create_escalation(**escalation.as_dict())
        campaign["escalation_id"] = queued["id"]

    return {"campaign_id": record["id"], "campaign": campaign}


@router.post("/api/products/{slug}/inquiries", summary="Capture a sales inquiry")
def create_inquiry(slug: str, inquiry: Inquiry) -> dict:
    """Record an inquiry and have the Sales AI draft follow-up outreach."""
    product = _require_product(slug)
    settings = get_settings()

    seats = max(1, inquiry.seats)
    annual = (product["price_month"] + product["price_setup"]) * 12
    estimated_value = round(annual * (seats / 10.0), 2)

    lead = store.create_lead(
        product_slug=product["slug"],
        product_name=product["name"],
        contact_name=inquiry.contact_name,
        email=inquiry.email,
        organisation=inquiry.organisation,
        message=inquiry.message,
        seats=seats,
        estimated_value=estimated_value,
    )

    outreach = run_sales_agent(
        target_customer_type=product["audience"],
        product_name=product["name"],
        offer=(
            f"We can start {product['name']} on a 30-day trial for your team of "
            f"about {seats}, with the {product['price_setup']} setup fee waived."
        ),
        variants=2,
    )

    escalation = build_lead_escalation(lead, settings)
    if escalation:
        queued = store.create_escalation(**escalation.as_dict())
        lead["escalation_id"] = queued["id"]

    return {
        "lead_id": lead["id"],
        "estimated_value": estimated_value,
        "escalated": escalation is not None,
        "escalation_id": lead.get("escalation_id"),
        "outreach": outreach,
    }


class QuotationRequest(BaseModel):
    """A request for a formal quotation (a demo request is the same pipeline)."""

    product_slug: str = Field(
        default="",
        max_length=80,
        description="Required for POST /api/quotations; taken from the URL for the by-product route.",
    )
    name: str = Field(..., min_length=2)
    email: str = Field(..., min_length=5)
    organisation: str = Field(default="", max_length=120)
    message: str = Field(default="", max_length=2000)
    seats: int = Field(default=1, ge=1, le=100000)
    term_months: int = Field(default=12, ge=1, le=120)
    discount_pct: float = Field(default=0.0, ge=0, le=100)
    support: bool = Field(default=False)
    send_email: bool = Field(default=True, description="Set false to generate without emailing.")


def _run_quote(payload: QuotationRequest, target_slug: str) -> dict:
    product = _require_product(target_slug)
    try:
        return run_quotation_pipeline(
            product,
            {
                "name": payload.name,
                "email": payload.email,
                "organisation": payload.organisation,
                "message": payload.message,
            },
            seats=payload.seats,
            term_months=payload.term_months,
            discount_pct=payload.discount_pct,
            support=payload.support,
            send_email=payload.send_email,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/quotations", summary="Request a quotation (AI pipeline)")
def create_quotation(payload: QuotationRequest) -> dict:
    """Run Marketing -> Sales -> Accounting -> e-mail.

    Returns the pipeline transcript so the caller can see which agent did what.
    """
    if not payload.product_slug.strip():
        raise HTTPException(status_code=400, detail="product_slug is required")
    return _run_quote(payload, payload.product_slug)


@router.post("/api/products/{slug}/quotation", summary="Request a quotation for a product")
def create_product_quotation(payload: QuotationRequest, slug: str) -> dict:
    """Same pipeline, with the product taken from the URL."""
    return _run_quote(payload, slug)


@router.post("/api/accounting/report")
def accounting_report(payload: dict) -> dict:
    """Convenience passthrough to the Accounting AI, with anomaly escalation."""
    settings = get_settings()
    entries = payload.get("entries") or []
    if not entries:
        raise HTTPException(status_code=400, detail="entries is required")

    report = run_accounting_agent(
        entries=entries,
        opening_balance=float(payload.get("opening_balance") or 0.0),
        currency=str(payload.get("currency") or "USD"),
    )

    from notifications.escalations import build_accounting_escalation

    escalation = build_accounting_escalation(report, settings)
    if escalation:
        queued = store.create_escalation(**escalation.as_dict())
        report["escalation_id"] = queued["id"]
    report["escalated"] = escalation is not None

    return report