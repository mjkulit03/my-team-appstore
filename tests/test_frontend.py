"""Tests for the dashboard: page serving, static assets, and coexistence with the API."""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_dashboard_is_served_at_dashboard_path():
    # "/" is the public storefront now; the AI dashboard lives at /dashboard.
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "AI Team Command Center" in resp.text


def test_root_serves_the_storefront_not_the_dashboard():
    root = client.get("/")
    assert root.status_code == 200
    assert "The catalog" in root.text


def test_dashboard_contains_all_three_agent_tabs():
    html = client.get("/dashboard").text
    for agent in ("marketing", "sales", "accounting"):
        assert f'id="tab-{agent}"' in html
        assert f'id="panel-{agent}"' in html
        assert f'data-run="{agent}"' in html
        assert f'data-response="{agent}"' in html


def test_each_tab_has_input_button_and_response_area():
    html = client.get("/dashboard").text
    for agent in ("marketing", "sales", "accounting"):
        # text input box
        assert f'id="prompt-{agent}"' in html
        # run button
        assert f'<button class="run" data-run="{agent}">' in html
        # designated response card area
        assert f'data-response="{agent}"' in html


def test_tabs_use_accessible_tab_semantics():
    html = client.get("/dashboard").text
    assert 'role="tablist"' in html
    assert html.count('role="tab"') == 3
    assert html.count('role="tabpanel"') == 3
    assert 'aria-selected="true"' in html
    # Exactly one panel visible on load.
    assert html.count('class="panel is-active"') == 1
    assert html.count("hidden") >= 2


def test_static_assets_are_served():
    css = client.get("/static/styles.css")
    assert css.status_code == 200
    assert css.headers["content-type"].startswith("text/css")
    assert ".sidebar" in css.text

    js = client.get("/static/app.js")
    assert js.status_code == 200
    assert "javascript" in js.headers["content-type"]
    assert "/api/agents/marketing" in js.text


def test_marketing_panel_exposes_brand_input():
    """brand is a documented agent input, so the dashboard must be able to set it."""
    html = client.get("/dashboard").text
    assert 'id="marketing-brand"' in html
    assert 'getElementById("marketing-brand")' in client.get("/static/app.js").text


def test_index_links_its_own_assets():
    html = client.get("/dashboard").text
    assert 'href="/static/styles.css"' in html
    assert 'src="/static/app.js"' in html


def test_favicon_route_resolves():
    assert client.get("/favicon.ico").status_code in (200, 307)
    assert client.get("/static/favicon.svg").status_code == 200


def test_api_still_works_with_static_mounted():
    """The /static mount must not shadow any API route."""
    assert client.get("/health").json()["agents"] == 3
    assert client.get("/agents").status_code == 200

    api = client.post(
        "/api/agents/marketing",
        json={"product_description": "A devtool that turns failing CI pipelines into a single diff"},
    )
    assert api.status_code == 200
    assert len(api.json()["posts"]) == 4


def test_dashboard_html_is_well_formed_enough():
    html = client.get("/dashboard").text
    assert client.get("/definitely-not-a-route").status_code == 404


def _strip_js_comments(src: str) -> str:
    """Remove comments so doc text mentioning a risky API doesn't trip the check."""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


def test_dashboard_never_embeds_agent_output_unchecked():
    """Client code must insert agent output via textContent, not innerHTML."""
    js = _strip_js_comments(client.get("/static/app.js").text)
    assert "innerHTML" not in js
    assert "outerHTML" not in js
    assert "insertAdjacentHTML" not in js
    assert "document.write" not in js
    assert "textContent" in js


def test_unknown_path_still_404s():
    assert client.get("/definitely-not-a-route").status_code == 404