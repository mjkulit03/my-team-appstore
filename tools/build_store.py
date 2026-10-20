"""Build the static app store at ``docs/index.html`` from the catalog.

The catalog is the single source of truth for which products exist; the admin's
price and label edits live in ``docs/store-content.json`` (see ``store_content``)
and are layered on top here. That keeps the GitHub Pages storefront unable to
drift from what the platform sells.

Usage:
    python tools/build_store.py                  # render docs/index.html
    python tools/build_store.py --init-content   # seed docs/store-content.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import catalog  # noqa: E402
import currency  # noqa: E402
import store_content  # noqa: E402

from jinja2 import Environment, FileSystemLoader, select_autoescape  # noqa: E402

DEFAULT_REPO = "https://github.com/mjkulit03/my-team-appstore"
DEFAULT_GITHUB = "https://github.com/mjkulit03"
DEFAULT_EMAIL = "jeff.manahan72@gmail.com"


def repo_slug(repo_url: str) -> str:
    """``https://github.com/owner/name`` -> ``owner/name``."""
    cleaned = repo_url.rstrip("/").removesuffix(".git")
    if "github.com/" in cleaned:
        return cleaned.split("github.com/", 1)[1].strip("/")
    return cleaned


def build(destination: Path | None = None, content: dict | None = None) -> Path:
    """Render the store and return the path written."""
    document = content if content is not None else store_content.load()
    source = store_content.apply(catalog.list_products(), document)

    products = []
    for product in source:
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

    repo_url = os.getenv("STORE_REPO_URL", DEFAULT_REPO)
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
        copy=store_content.page_copy(document, len(products)),
        copy_defaults=store_content.PAGE_COPY_DEFAULTS,
        bundle_month=f"{bundle_month:,}",
        bundle_setup=f"{bundle_setup:,}",
        bundle_usd=f"{bundle_usd:,.2f}",
        github_url=os.getenv("STORE_GITHUB_URL", DEFAULT_GITHUB),
        repo_url=repo_url,
        repo_slug=repo_slug(repo_url),
        content_path=store_content.CONTENT_PATH.relative_to(ROOT).as_posix(),
        content_json=store_content.dumps(document),
        products_json=json.dumps(
            [
                {
                    "slug": p["slug"],
                    "icon": p["icon"],
                    "name": p["name"],
                    "tagline": p["tagline"],
                    "category": p["category"],
                    "price_month": p["price_month"],
                    "price_setup": p["price_setup"],
                }
                for p in products
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        email=os.getenv("STORE_EMAIL", DEFAULT_EMAIL),
    )

    target = destination or (ROOT / "docs" / "index.html")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html, encoding="utf-8")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render the static app store.")
    parser.add_argument(
        "--init-content",
        action="store_true",
        help="seed docs/store-content.json from the catalog (refuses to overwrite)",
    )
    args = parser.parse_args(argv)

    if args.init_content:
        if store_content.CONTENT_PATH.exists():
            print(f"{store_content.CONTENT_PATH} already exists; left untouched.")
        else:
            store_content.save(store_content.document_from_catalog())
            print(f"Wrote {store_content.CONTENT_PATH}")

    written = build()
    print(f"Wrote {written} ({written.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
