"""Tests for the admin-editable store content (prices, labels, page copy).

The published store must degrade to the catalog whenever the content file is
missing, partial or nonsense — an admin typo may never publish a broken page or
an absurd price.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

import catalog
import store_content

ROOT = Path(__file__).resolve().parent.parent


def load_build_module():
    """Import tools/build_store.py, which is a script rather than a package."""
    spec = importlib.util.spec_from_file_location("build_store", ROOT / "tools" / "build_store.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sample_document() -> dict:
    return store_content.document_from_catalog()


# --------------------------------------------------------------- defaults


def test_missing_file_means_catalog_defaults(tmp_path):
    content = store_content.load(tmp_path / "nope.json")
    assert content["prices"] == {}
    assert content["labels"] == {}
    assert content["copy"] == {}


def test_document_from_catalog_covers_every_product():
    document = store_content.document_from_catalog()
    slugs = {p["slug"] for p in catalog.list_products()}
    assert set(document["prices"]) == slugs
    assert set(document["labels"]) == slugs
    assert len(slugs) == 13


def test_page_copy_substitutes_count():
    copy = store_content.page_copy({}, count=13)
    assert "13 systems · one store" == copy["hero_eyebrow"]
    assert "13 business systems" in copy["footer_line"]
    assert "{count}" not in copy["bundle_body"]


def test_admin_copy_overrides_default_text():
    document = store_content.normalize({"copy": {"hero_headline": "Buy software today."}})
    assert store_content.page_copy(document)["hero_headline"] == "Buy software today."
    # Untouched keys keep their defaults.
    assert store_content.page_copy(document)["catalog_heading"] == "The catalog"


# --------------------------------------------------------------- validation


def test_prices_and_labels_override_the_catalog():
    document = store_content.normalize(
        {
            "prices": {"hardware-inventory-system": {"price_month": 1990, "price_setup": 12000}},
            "labels": {"hardware-inventory-system": {"name": "Hardware Tracker"}},
        }
    )
    merged = store_content.apply(catalog.list_products(), document)
    product = next(p for p in merged if p["slug"] == "hardware-inventory-system")
    assert product["price_month"] == 1990
    assert product["price_setup"] == 12000
    assert product["name"] == "Hardware Tracker"
    # Untouched fields still come from the catalog.
    original = catalog.find_product("hardware-inventory-system")
    assert product["tagline"] == original["tagline"]
    assert product["features"] == original["features"]


@pytest.mark.parametrize(
    "raw, expected",
    [("1,490", 1490), ("₱1490", 1490), (" PHP 990 ", 990), (1490.0, 1490), ("", None), ("abc", None)],
)
def test_price_parsing_accepts_common_typing(raw, expected):
    document = store_content.normalize({"prices": {"offline-pos-system": {"price_month": raw}}})
    assert document["prices"].get("offline-pos-system", {}).get("price_month") == expected


@pytest.mark.parametrize("bad", [-1, -1490, 10_000_001, "many", None, True])
def test_invalid_prices_are_dropped(bad):
    document = store_content.normalize({"prices": {"offline-pos-system": {"price_month": bad}}})
    assert "offline-pos-system" not in document["prices"]


def test_unknown_slugs_and_keys_are_ignored():
    document = store_content.normalize(
        {
            "prices": {"not-a-product": {"price_month": 100}},
            "labels": {"offline-pos-system": {"price_month": 5, "name": "POS"}},
            "copy": {"not_a_field": "x"},
        }
    )
    assert "not-a-product" not in document["prices"]
    assert document["labels"]["offline-pos-system"] == {"name": "POS"}
    assert document["copy"] == {}


def test_overlong_text_falls_back_to_catalog():
    document = store_content.normalize({"labels": {"offline-pos-system": {"name": "x" * 81}}})
    assert "offline-pos-system" not in document["labels"]


def test_blank_text_falls_back_to_catalog():
    document = store_content.normalize({"labels": {"offline-pos-system": {"name": "   "}}})
    assert "offline-pos-system" not in document["labels"]


def test_apply_never_mutates_the_catalog():
    before = json.dumps(catalog.list_products(), sort_keys=True, default=str)
    store_content.apply(
        catalog.list_products(),
        store_content.normalize({"prices": {"offline-pos-system": {"price_month": 1}}}),
    )
    after = json.dumps(catalog.list_products(), sort_keys=True, default=str)
    assert before == after


# --------------------------------------------------------------- file I/O


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "store-content.json"
    document = sample_document()
    document["prices"]["offline-pos-system"] = {"price_month": 2500, "price_setup": 11000}
    store_content.save(document, path)

    reloaded = store_content.load(path)
    assert reloaded["prices"]["offline-pos-system"] == {"price_month": 2500, "price_setup": 11000}
    # Saved files are human-readable and end with a newline.
    assert path.read_text(encoding="utf-8").endswith("\n")


def test_malformed_json_is_reported(tmp_path):
    path = tmp_path / "store-content.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(store_content.ContentError):
        store_content.load(path)


# --------------------------------------------------------------- rendering


def test_built_page_uses_admin_prices_and_copy(tmp_path):
    build_store = load_build_module()
    document = store_content.document_from_catalog()
    document["prices"]["offline-pos-system"] = {"price_month": 2500, "price_setup": 11000}
    document["labels"]["offline-pos-system"] = {"name": "Counter POS", "tagline": "Ring up sales offline."}
    document["copy"] = {"hero_headline": "Software you can afford."}

    destination = build_store.build(tmp_path / "index.html", content=store_content.normalize(document))
    html = destination.read_text(encoding="utf-8")

    assert "Counter POS" in html
    assert "Ring up sales offline." in html
    assert "₱2,500" in html
    assert "Software you can afford." in html


def test_built_page_exposes_admin_login_and_edit_data(tmp_path):
    build_store = load_build_module()
    destination = build_store.build(tmp_path / "index.html")
    html = destination.read_text(encoding="utf-8")

    assert 'id="admin-open"' in html
    assert 'id="admin-login"' in html
    assert 'id="admin-editor"' in html
    assert "docs/store-content.json" in html
    # The editor boots from the published document, so the page must embed it.
    assert 'id="store-content"' in html
    assert 'id="store-products"' in html
    # No real token may be baked into the page (the input placeholder is fine).
    assert not re.search(r"(github_pat_[A-Za-z0-9_]{20,}|ghp_[A-Za-z0-9]{20,})", html)


def test_committed_content_file_matches_the_catalog():
    """The file in the repo must be valid and cover every product."""
    stored = store_content.load()
    slugs = {p["slug"] for p in catalog.list_products()}
    assert set(stored["labels"]) == slugs
    assert set(stored["prices"]) == slugs
