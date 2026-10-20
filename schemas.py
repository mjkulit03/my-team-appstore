"""Pydantic request models for the three agent endpoints."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class MarketingRequest(BaseModel):
    product_description: str = Field(
        ...,
        min_length=20,
        description="What the product does. Drives all generated copy.",
        examples=[
            "A SaaS platform that automates invoice reconciliation for small e-commerce "
            "merchants and syncs receipts directly into QuickBooks"
        ],
    )
    product_name: str | None = Field(
        default=None,
        description="Optional override; inferred from the description when omitted.",
        json_schema_extra={"examples": ["Ledgerly"]},
    )
    brand: str | None = Field(
        default=None,
        json_schema_extra={"examples": ["Ledgerly Inc"]},
    )
    tone: Literal["confident", "friendly", "bold", "technical"] = Field(
        default="confident", description="Voice applied to every generated post."
    )
    channels: list[Literal["x", "linkedin", "instagram", "facebook"]] | None = Field(
        default=None,
        description="Which channels to generate. Defaults to all four.",
        examples=[["x", "linkedin"]],
    )


class SalesRequest(BaseModel):
    target_customer_type: str = Field(
        ...,
        min_length=3,
        description="Who to sell to. Industry is detected from this text.",
        examples=["small dental clinic owners"],
    )
    product_name: str = Field(default="our product")
    offer: str = Field(
        default="Happy to set up a 15-minute demo with no commitment.",
        min_length=3,
        description="The single call to action reused across every email.",
    )
    sender_name: str = Field(default="Alex")
    sender_company: str = Field(default="Acme")
    tone: Literal["direct", "warm", "consultative"] = Field(default="direct")
    variants: int = Field(default=3, ge=1, le=4, description="How many email variants to produce.")


class AccountingEntry(BaseModel):
    type: Literal["income", "expense"]
    amount: float = Field(..., description="Positive magnitude; direction comes from `type`.", examples=[1250.00])
    category: str = Field(..., min_length=1, examples=["Subscription revenue"])
    description: str = Field(default="", examples=["Annual plan, 12 customers"])
    date: str | None = Field(default=None, description="Optional ISO date, YYYY-MM-DD.", examples=["2026-03-01"])


class AccountingRequest(BaseModel):
    entries: list[AccountingEntry] = Field(..., min_length=1)
    opening_balance: float = Field(default=0.0, description="Cash on hand at period start.")
    currency: str = Field(default="USD", min_length=3, max_length=4)
    top_n: int = Field(default=5, ge=1, le=50, description="How many largest expenses to list.")