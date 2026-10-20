"""Build the static app store at ``docs/index.html`` from the catalog.

The catalog is the single source of truth, so the GitHub Pages storefront can
never drift from the products the FastAPI application sells.

Usage:
    python tools/build_store.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import catalog  # noqa: E402
import currency  # noqa: E402

from jinja2 import Environment, FileSystemLoader, select_autoescape  # noqa: E402

DEFAULT_REPO = "https://github.com/mjkulit03/my-team-appstore"
DEFAULT_GITHUB = "https://github.com/mjkulit03"
DEFAULT_EMAIL = "jeff.manahan72@gmail.com"


def build(destination: Path | None = None) -> Path:
    """Render the store and return the path written."""
    products = []
    for product in catalog.list_products():
        usd = currency.convert(product["price_month"], "PHP", "USD") or 0.0
        products.append(
            {
                **product,
                "price_display": f"{product['price_month']:,}",
                "setup_display": f"{product['price_setup']:,}",
                "usd_display": f"{usd:,.2f}",
            }
        )

    bundle_month = sum(p["price_month"] for p in products)
    bundle_setup = sum(p["price_setup"] for p in products)
    bundle_usd = currency.convert(bundle_month, "PHP", "USD") or 0.0

    env = Environment(
        loader=FileSystemLoader(ROOT / "templates"),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    html = env.get_template("appstore.html").render(
        products=products,
        categories=sorted({p["category"] for p in products}),
        count=len(products),
        bundle_month=f"{bundle_month:,}",
        bundle_setup=f"{bundle_setup:,}",
        bundle_usd=f"{bundle_usd:,.2f}",
        github_url=os.getenv("STORE_GITHUB_URL", DEFAULT_GITHUB),
        repo_url=os.getenv("STORE_REPO_URL", DEFAULT_REPO),
        email=os.getenv("STORE_EMAIL", DEFAULT_EMAIL),
    )

    target = destination or (ROOT / "docs" / "index.html")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html, encoding="utf-8")
    return target


if __name__ == "__main__":
    written = build()
    print(f"Wrote {written} ({written.stat().st_size:,} bytes)")
