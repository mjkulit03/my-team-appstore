"""Tests for the store editor behind the control-panel login.

The hosted editor replaces the static site's GitHub-token dialog: an
administrator signs in with a username and password, the app validates the form,
writes ``docs/store-content.json`` and rebuilds ``docs/index.html``. Nothing here
may require a browser token.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import catalog
import store
import store_content
import users
from api import storeadmin
from main import app

ROOT = Path(__file__).resolve().parent.parent
PASSWORD = "test-control-password"


def load_build_module():
    spec = importlib.util.spec_from_file_location("build_store_admin", ROOT / "tools" / "build_store.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    for key in ("SEED_DEMO_USERS", "DEMO_USER_PASSWORD", "CONTROL_PANEL_PASSWORD",
                "STORE_GITHUB_TOKEN", "STORE_REPO", "STORE_ADMIN_URL"):
        monkeypatch.delenv(key, raising=False)
    store.reset_for_tests()

    content = tmp_path / "docs" / "store-content.json"
    content.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(store_content, "CONTENT_PATH", content)

    rebuilds: list[int] = []
    monkeypatch.setattr(storeadmin, "_rebuild", lambda: rebuilds.append(1))

    yield {"content": content, "rebuilds": rebuilds}
    store.reset_for_tests()


def client_for(username: str, role: str = "admin") -> TestClient:
    users.create_user(username, PASSWORD, role, username.title())
    c = TestClient(app)
    c.post("/control/login", data={"username": username, "password": PASSWORD}, follow_redirects=False)
    return c


def form_for(document: dict | None = None) -> dict[str, str]:
    """A complete form submission: every product and copy field, catalog values."""
    data: dict[str, str] = {}
    for product in catalog.list_products():
        for key in ("name", "tagline", "category", "price_month", "price_setup"):
            data[f"product.{product['slug']}.{key}"] = str(product[key])
    for key, value in store_content.PAGE_COPY_DEFAULTS.items():
        data[f"copy.{key}"] = value
    return data


def saved_document(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ------------------------------------------------------------------- access


def test_editor_requires_a_login(isolated_state):
    response = TestClient(app).get("/control/store", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/control/login?next=%2Fcontrol%2Fstore"


def test_login_returns_the_administrator_to_the_editor(isolated_state):
    users.create_user("boss", PASSWORD, "admin", "Boss")
    c = TestClient(app)
    response = c.post(
        "/control/login",
        data={"username": "boss", "password": PASSWORD, "next": "/control/store"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/control/store"


def test_login_refuses_an_offsite_next(isolated_state):
    users.create_user("boss", PASSWORD, "admin", "Boss")
    c = TestClient(app)
    response = c.post(
        "/control/login",
        data={"username": "boss", "password": PASSWORD, "next": "https://evil.example/steal"},
        follow_redirects=False,
    )
    assert response.headers["location"] == "/control/overview"

    form = c.get("/control/login", params={"next": "//evil.example"}).text
    assert 'name="next"' not in form


def test_analyst_can_read_but_not_save(isolated_state):
    c = client_for("analyst", role="analyst")
    page = c.get("/control/store")
    assert page.status_code == 200
    assert "changing prices needs an administrator or operator" in page.text

    response = c.post("/control/store", data=form_for())
    assert response.status_code == 403
    assert not isolated_state["content"].exists()
    assert isolated_state["rebuilds"] == []


# --------------------------------------------------------------------- page


def test_editor_lists_every_product_and_copy_field(isolated_state):
    c = client_for("boss")
    page = c.get("/control/store")
    assert page.status_code == 200
    for product in catalog.list_products():
        assert f'name="product.{product["slug"]}.price_month"' in page.text
    for key in store_content.COPY_LABELS:
        assert f'name="copy.{key}"' in page.text
    # No GitHub token anywhere: this is the password-based editor.
    assert "github_pat" not in page.text


# ------------------------------------------------------------------- saving


def test_save_writes_overrides_and_rebuilds(isolated_state):
    c = client_for("boss")
    data = form_for()
    data["product.cybersecurity-games.price_month"] = "1590"
    data["product.cybersecurity-games.name"] = "Cyber Games & Awareness"
    data["copy.hero_headline"] = "Run the whole business on day one."

    response = c.post("/control/store", data=data, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/control/store?notice=")

    document = saved_document(isolated_state["content"])
    assert document["prices"]["cybersecurity-games"]["price_month"] == 1590
    assert document["labels"]["cybersecurity-games"]["name"] == "Cyber Games & Awareness"
    assert document["copy"]["hero_headline"] == "Run the whole business on day one."
    assert isolated_state["rebuilds"] == [1]


def test_saved_price_reaches_the_rendered_page(isolated_state, tmp_path):
    c = client_for("boss")
    data = form_for()
    data["product.cybersecurity-games.price_month"] = "1590"
    data["product.cybersecurity-games.name"] = "Cyber Games & Awareness"
    c.post("/control/store", data=data, follow_redirects=False)

    target = tmp_path / "index.html"
    load_build_module().build(destination=target, content=store_content.load())
    html = target.read_text(encoding="utf-8")
    assert "1,590" in html
    assert "Cyber Games &amp; Awareness" in html  # the label edit too


def test_unchanged_form_leaves_no_overrides(isolated_state):
    c = client_for("boss")
    c.post("/control/store", data=form_for(), follow_redirects=False)

    document = saved_document(isolated_state["content"])
    assert document["prices"] == {}
    assert document["labels"] == {}
    assert document["copy"] == {}


def test_blank_fields_fall_back_to_the_catalog(isolated_state):
    c = client_for("boss")
    data = form_for()
    data["product.cybersecurity-games.name"] = ""
    data["product.cybersecurity-games.price_month"] = ""
    c.post("/control/store", data=data, follow_redirects=False)

    document = saved_document(isolated_state["content"])
    assert "cybersecurity-games" not in document["labels"]
    assert "cybersecurity-games" not in document["prices"]


def test_invalid_price_is_refused_and_nothing_is_written(isolated_state):
    c = client_for("boss")
    data = form_for()
    data["product.cybersecurity-games.price_month"] = "-5"

    response = c.post("/control/store", data=data)
    assert response.status_code == 400
    assert "whole peso amount" in response.text
    assert not isolated_state["content"].exists()  # no half-bad file published
    assert isolated_state["rebuilds"] == []


def test_rejected_save_keeps_what_was_typed(isolated_state):
    c = client_for("boss")
    data = form_for()
    data["product.cybersecurity-games.price_month"] = "12,34x"

    response = c.post("/control/store", data=data)
    assert response.status_code == 400
    assert 'value="12,34x"' in response.text


def test_publish_failure_keeps_the_local_save(isolated_state, monkeypatch):
    monkeypatch.setenv("STORE_REPO", "owner/repo")
    monkeypatch.setenv("STORE_GITHUB_TOKEN", "ghp_fake")

    def boom(_document, _message=None):
        raise ValueError("GitHub refused to write store-content.json (403).")

    monkeypatch.setattr(storeadmin.store_publish, "publish", boom)

    c = client_for("boss")
    data = form_for()
    data["product.cybersecurity-games.price_month"] = "1590"
    response = c.post("/control/store", data=data, follow_redirects=False)

    assert response.status_code == 303
    assert saved_document(isolated_state["content"])["prices"]["cybersecurity-games"]["price_month"] == 1590
    notice = response.headers["location"]
    assert "mirror" in notice


# ---------------------------------------------------- the published Admin link


def test_static_page_links_to_the_hosted_editor(monkeypatch, tmp_path):
    monkeypatch.setenv("STORE_ADMIN_URL", "/control/store")
    target = tmp_path / "index.html"
    load_build_module().build(destination=target, content={})
    html = target.read_text(encoding="utf-8")

    assert 'id="admin-link"' in html
    assert 'href="/control/store"' in html
    assert 'id="admin-token"' not in html  # no token dialog on a hosted deploy


def test_static_page_keeps_the_token_editor_without_a_host(monkeypatch, tmp_path):
    monkeypatch.delenv("STORE_ADMIN_URL", raising=False)
    target = tmp_path / "index.html"
    load_build_module().build(destination=target, content={})
    html = target.read_text(encoding="utf-8")

    assert 'id="admin-open"' in html
    assert 'id="admin-token"' in html


# --------------------------------------------------------------- validation


def test_validate_explains_each_problem():
    problems = store_content.validate(
        {
            "prices": {"cybersecurity-games": {"price_month": "abc"}, "nope": {"price_month": 1}},
            "labels": {catalog.list_products()[0]["slug"]: {"name": "x" * 500}},
            "copy": {"hero_headline": "", "made_up": "text"},
        }
    )
    assert any("whole peso amount" in p for p in problems)
    assert any("Unknown product 'nope'" in p for p in problems)
    assert any("1-80 characters" in p for p in problems)
    assert any("Hero headline must be text" in p for p in problems)
    assert any("Unknown page-copy field 'made_up'" in p for p in problems)


def test_validate_accepts_a_clean_document():
    assert store_content.validate(store_content.document_from_catalog()) == []
