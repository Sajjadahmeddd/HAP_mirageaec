"""HSTS follows the request's scheme, not the platform.

It used to be sent whenever the RENDER variable was set, and compose set
RENDER=1 on the VPS to keep it. Now it is sent exactly when the request
arrived over https: directly, or through a trusted proxy's X-Forwarded-Proto
(TRUSTED_PROXIES, backend/maec_auth/proxy.py) — as MAEC One Core decides it.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import app

HSTS = "Strict-Transport-Security"
VIA_CADDY = {"X-Forwarded-Proto": "https", "X-Forwarded-Host": "et.mirageaec.com"}


def test_https_through_a_trusted_proxy_gets_hsts(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXIES", "testclient")
    response = TestClient(app).get("/api/health", headers=VIA_CADDY)
    assert response.headers[HSTS] == "max-age=31536000; includeSubDomains"


def test_an_untrusted_peer_claiming_https_gets_none(monkeypatch):
    """The control: the same header from a peer outside TRUSTED_PROXIES is
    anyone's claim, and pinning a browser on a claim is not on."""
    monkeypatch.setenv("TRUSTED_PROXIES", "172.30.81.0/24")
    assert HSTS not in TestClient(app).get("/api/health", headers=VIA_CADDY).headers


def test_plain_http_gets_none(monkeypatch):
    """A developer's machine: asserting it would pin https://localhost."""
    monkeypatch.delenv("TRUSTED_PROXIES", raising=False)
    assert HSTS not in TestClient(app).get("/api/health").headers


def test_a_direct_https_request_gets_hsts():
    assert HSTS in TestClient(app, base_url="https://testserver").get("/api/health").headers


def test_render_no_longer_decides_it(monkeypatch):
    """RENDER set, request over http: no HSTS. Before, this sent it."""
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.delenv("TRUSTED_PROXIES", raising=False)
    assert HSTS not in TestClient(app).get("/api/health").headers


def test_hsts_rides_on_a_refusal_too(monkeypatch, app_client):
    """security_headers is outside the gate, so a signed-out stranger arriving
    over https is pinned as well."""
    monkeypatch.setenv("TRUSTED_PROXIES", "testclient")
    refused = app_client.get("/api/airsizer/config", headers=VIA_CADDY)
    assert refused.status_code == 401
    assert HSTS in refused.headers
