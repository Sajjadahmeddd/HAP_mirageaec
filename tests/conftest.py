"""Fixtures for the backend tests: a MAEC One Core that exists only in this process.

Engineering Tools asks Core's /api/gate/check about the browser's cookie on
every request. These tests must not reach a real Core, so the gate's HTTP
transport is swapped for an httpx.MockTransport that answers the way Core's
router_gate.py does:

  * a wrong app key or secret          -> 403 bad_app
  * no cookie, or one naming no session -> 401 not_signed_in, with a login_url
  * a session the test marked refused  -> that status and reason (403 no_access)
  * a valid session                    -> 200 {user, org_id, permissions, nav_hidden}

`fake_core.down = True` makes every call fail to connect; `fake_core.status`
forces some other answer (a 500, say). Every call Core received is kept in
`fake_core.calls`, so a test can see exactly what the gate forwarded.

`app_client` is a stranger. `engineer_client` carries a valid session cookie
for an employee holding view/convert/export on every module, which is what
the router tests need to reach the routers at all.

The HAP PDF fixtures are in the repository-root conftest.py.
"""

from __future__ import annotations

from urllib.parse import quote

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.maec_auth import gate

CORE_URL = "http://core.test"
CORE_PUBLIC_URL = "http://auth.test"
APP_KEY = "engineering"
GATE_SECRET = "test-gate-secret-never-real-0123456789"

# MAEC One Core's session cookie (Core 830e902). The OLD Engineering Tools
# keeps its own "maec_session"; the two names must differ.
SESSION_COOKIE = "maec_one_session"
OLD_APP_COOKIE = "maec_session"
ENGINEER_SESSION = "engineer-session-id"

MODULES = ("hapext", "airsizer", "hapaudit", "rebadge")
ACTIONS = ("view", "convert", "export")
ALL_PERMISSIONS = [f"engineering:{m}:{a}" for m in MODULES for a in ACTIONS]


def _cookie(header: str, name: str) -> str | None:
    for part in header.split(";"):
        key, _, value = part.strip().partition("=")
        if key == name:
            return value
    return None


class FakeCore:
    """The answers Core's /api/gate/check would give."""

    def __init__(self) -> None:
        self.calls: list[httpx.Request] = []
        self.down = False
        self.status: int | None = None
        # session id -> the person it belongs to
        self.sessions: dict[str, dict] = {
            ENGINEER_SESSION: {
                "user": {"id": "user-engineer", "email": "engineer@mirageaec.com",
                         "name": "Test Engineer"},
                "org_id": "org-mirage",
                "permissions": list(ALL_PERMISSIONS),
                "nav_hidden": [],
            },
        }
        # session id -> (status, reason): signed in, but refused
        self.refused: dict[str, tuple[int, str]] = {}

    def engineer(self) -> dict:
        return self.sessions[ENGINEER_SESSION]

    def _refuse(self, request: httpx.Request, status: int, reason: str) -> httpx.Response:
        wanted = request.headers.get("x-original-url", "")
        login_url = f"{CORE_PUBLIC_URL}/" + (f"?next={quote(wanted, safe='')}" if wanted else "")
        return httpx.Response(status, json={"reason": reason, "login_url": login_url})

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        if self.down:
            raise httpx.ConnectError("Core is down", request=request)
        if self.status is not None:
            return httpx.Response(self.status, text="Internal Server Error")
        if (request.headers.get("x-maec-app") != APP_KEY
                or request.headers.get("x-maec-gate-secret") != GATE_SECRET):
            return self._refuse(request, 403, "bad_app")
        sid = _cookie(request.headers.get("cookie", ""), SESSION_COOKIE)
        if sid in self.refused:
            return self._refuse(request, *self.refused[sid])
        if sid not in self.sessions:
            return self._refuse(request, 401, "not_signed_in")
        return httpx.Response(200, json=self.sessions[sid])


@pytest.fixture
def fake_core() -> FakeCore:
    return FakeCore()


@pytest.fixture(autouse=True)
def gate_settings(monkeypatch, fake_core):
    """Point the gate at the fake Core.

    Autouse, because every test in this directory runs against an app whose
    settings would otherwise be read from the developer's own environment —
    and whose pooled HTTP client would otherwise leak between tests.
    """
    monkeypatch.setenv("CORE_URL", CORE_URL)
    monkeypatch.setenv("MAEC_APP_KEY", APP_KEY)
    monkeypatch.setenv("MAEC_GATE_SECRET", GATE_SECRET)
    monkeypatch.delenv("RENDER", raising=False)
    # Optional settings a developer may have exported: tests that need them
    # set them, so a value from the machine cannot change an answer.
    monkeypatch.delenv("CORE_PUBLIC_URL", raising=False)
    monkeypatch.delenv("TRUSTED_PROXIES", raising=False)
    monkeypatch.setattr(gate, "transport", httpx.MockTransport(fake_core.handler))
    gate.reset_client()
    yield
    gate.reset_client()


@pytest.fixture
def app_client():
    """A browser that has not signed in at MAEC One."""
    from backend.main import app
    return TestClient(app)


@pytest.fixture
def engineer_client():
    """A browser carrying Core's session cookie for an engineer with
    view/convert/export on every module."""
    from backend.main import app
    client = TestClient(app)
    client.cookies.set(SESSION_COOKIE, ENGINEER_SESSION)
    return client
