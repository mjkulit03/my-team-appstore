"""Publish store edits to the GitHub repository that hosts the Pages mirror.

The browser-based editor on the static site has to ask for a GitHub token,
because GitHub Pages has no server to check a password. When the platform is
hosted, that changes: the FastAPI app checks the username and password, and the
one credential that can write to the repository stays in the server's
environment. It is never sent to a browser.

Publishing is optional. Set ``STORE_GITHUB_TOKEN`` (a token with *Contents: Read
and write* on the store repository) and ``STORE_REPO`` to switch it on; without
them the editor still saves and rebuilds the local store, it just does not push.

Only ``docs/store-content.json`` is pushed. The Pages workflow rebuilds
``docs/index.html`` from it on every push, so no generated HTML is committed
from here.
"""

from __future__ import annotations

import base64
import os

import httpx
import store_content

GITHUB_API = "https://api.github.com"
TIMEOUT = 20.0
#: Where the file lives in the repository — the path GitHub Pages builds from.
CONTENT_REPO_PATH = "docs/store-content.json"


class PublishError(RuntimeError):
    """Raised when GitHub rejects the commit."""


def repo() -> str:
    """``owner/name`` of the store repository, or '' when unset."""
    return (os.getenv("STORE_REPO") or "").strip().strip("/")


def branch() -> str:
    return (os.getenv("STORE_BRANCH") or "main").strip() or "main"


def configured() -> bool:
    """True when a push is possible: both a repository and a token are set."""
    return bool(repo() and (os.getenv("STORE_GITHUB_TOKEN") or "").strip())


def publish(document: dict, message: str | None = None) -> str:
    """Commit the content file to the repository. Returns the commit sha."""
    token = (os.getenv("STORE_GITHUB_TOKEN") or "").strip()
    target = repo()
    if not token or not target:
        raise PublishError("STORE_GITHUB_TOKEN and STORE_REPO are not both set.")

    path = CONTENT_REPO_PATH
    api = f"{GITHUB_API}/repos/{target}/contents/{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    with httpx.Client(timeout=TIMEOUT, headers=headers) as client:
        existing = client.get(api, params={"ref": branch()})
        sha = None
        if existing.status_code == 200:
            sha = (existing.json() or {}).get("sha")
        elif existing.status_code != 404:
            raise PublishError(_explain(existing, "read"))

        payload = {
            "message": message or "Update store prices and labels from the control panel",
            "content": base64.b64encode(store_content.dumps(document).encode("utf-8")).decode("ascii"),
            "branch": branch(),
        }
        if sha:
            payload["sha"] = sha
        response = client.put(api, json=payload)
        if response.status_code not in (200, 201):
            raise PublishError(_explain(response, "write"))
        return ((response.json() or {}).get("commit") or {}).get("sha", "")


def _explain(response: httpx.Response, action: str) -> str:
    try:
        detail = (response.json() or {}).get("message") or ""
    except ValueError:
        detail = ""
    return (
        f"GitHub refused to {action} {store_content.CONTENT_PATH.name} "
        f"({response.status_code}{': ' + detail if detail else ''})."
    )
