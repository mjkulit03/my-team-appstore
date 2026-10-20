"""FastAPI application: storefront, AI employees, control panel and dashboard.

Run with:
    uvicorn main:app --reload --port 8000

Then open:
    Storefront        http://127.0.0.1:8000/
    AI dashboard      http://127.0.0.1:8000/dashboard
    Control panel     http://127.0.0.1:8000/control/login
    Interactive docs  http://127.0.0.1:8000/docs
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from agents import run_accounting_agent, run_marketing_agent, run_sales_agent
from api import control, pages, storefront
from auth import add_session_middleware
from schemas import AccountingRequest, MarketingRequest, SalesRequest
import users

STATIC_DIR = Path(__file__).resolve().parent / "static"
DOCS_DIR = Path(__file__).resolve().parent / "docs"

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Guarantee a way in: optional demo users first, then a bootstrap admin.

    Order matters. Seeding demo accounts first means an explicitly enabled demo
    set is not shadowed by the bootstrap `admin` built from
    CONTROL_PANEL_PASSWORD, which would use a different password.
    """
    try:
        users.seed_demo_users()
        users.ensure_bootstrap_admin()
    except Exception:  # never block startup on a store problem
        pass
    yield


app = FastAPI(
    lifespan=lifespan,
    title="My Team \u2014 Simulated Agents",
    description=(
        "Three rule-based 'AI employees' (Marketing, Sales, Accounting). "
        "Each is a pure function wrapped in an HTTP endpoint \u2014 no LLM, no API keys."
    ),
    version="1.0.0",
)

AGENTS = [
    {
        "id": "marketing",
        "name": "Marketing Agent",
        "endpoint": "/api/agents/marketing",
        "takes": "product_description",
        "returns": "social media posts (x, linkedin, instagram, facebook) + strategy points",
    },
    {
        "id": "sales",
        "name": "Sales Agent",
        "endpoint": "/api/agents/sales",
        "takes": "target_customer_type",
        "returns": "cold-outreach email variants, follow-up sequence, targeting notes",
    },
    {
        "id": "accounting",
        "name": "Accounting Agent",
        "endpoint": "/api/agents/accounting",
        "takes": "raw income/expense entries",
        "returns": "financial status report with totals, category breakdowns and alerts",
    },
]


def _guard(fn, *args, **kwargs):
    """Translate a ValueError from an agent into a clean 400."""
    try:
        return fn(*args, **kwargs)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/dashboard", include_in_schema=False)
def dashboard():
    """Serve the AI employees dashboard page."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/app-store", include_in_schema=False)
def app_store():
    """Serve the static, GitHub Pages-ready app store."""
    page = DOCS_DIR / "index.html"
    if not page.exists():
        raise HTTPException(status_code=404, detail="App store has not been built")
    return FileResponse(page)


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return RedirectResponse(url="/static/favicon.svg")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "agents": len(AGENTS)}


@app.get("/agents")
def list_agents() -> dict:
    return {"agents": AGENTS}


@app.post("/api/agents/marketing", tags=["marketing"], summary="Marketing Agent")
def marketing_agent(request: MarketingRequest) -> dict:
    """Turn a product description into social posts and strategy points."""
    return _guard(
        run_marketing_agent,
        product_description=request.product_description,
        product_name=request.product_name,
        brand=request.brand,
        tone=request.tone,
        channels=list(request.channels) if request.channels else None,
    )


@app.post("/api/agents/sales", tags=["sales"], summary="Sales Agent")
def sales_agent(request: SalesRequest) -> dict:
    """Turn a target customer type into cold-outreach emails and a follow-up sequence."""
    return _guard(
        run_sales_agent,
        target_customer_type=request.target_customer_type,
        product_name=request.product_name,
        offer=request.offer,
        sender_name=request.sender_name,
        sender_company=request.sender_company,
        tone=request.tone,
        variants=request.variants,
    )


@app.post("/api/agents/accounting", tags=["accounting"], summary="Accounting Agent")
def accounting_agent(request: AccountingRequest) -> dict:
    """Turn raw income/expense entries into a summarised financial status report."""
    return _guard(
        run_accounting_agent,
        entries=[entry.model_dump() for entry in request.entries],
        opening_balance=request.opening_balance,
        currency=request.currency,
        top_n=request.top_n,
    )


# ---- storefront, control panel and AI dashboard pages ----
add_session_middleware(app)
app.include_router(storefront.router)
app.include_router(control.router)
app.include_router(control.users_router)
app.include_router(pages.router)


# Mounted last so it never shadows the API routes above.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")