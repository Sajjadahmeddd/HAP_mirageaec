"""The real address behind the front door: Caddy -> nginx -> uvicorn.

Behind the proxies this process sees plain http and an internal host. Core
builds the sign-in's `next` from the X-Original-URL the gate sends, and only
follows a `next` on an app's own https:// address, so that URL has to be the
one the browser used.

backend/maec_auth/proxy.py applies X-Forwarded-Proto and X-Forwarded-Host
only when the request's socket peer is in TRUSTED_PROXIES. The test client's
peer address is the literal "testclient", so naming it trusts it, and naming
anything else does not.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from backend.maec_auth import proxy
from backend.main import app

from conftest import ENGINEER_SESSION, SESSION_COOKIE

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = "et.mirageaec.com"

# What nginx sends on, having received Caddy's request: the internal hop is
# plain http to the backend container, and Caddy's headers ride along.
THROUGH_THE_PROXIES = {
    "Host": "backend:8000",
    "X-Forwarded-Proto": "https",
    "X-Forwarded-Host": PUBLIC,
    "X-Forwarded-For": "203.0.113.7",
}


def _client(*, signed_in: bool = True) -> TestClient:
    client = TestClient(app)
    if signed_in:
        client.cookies.set(SESSION_COOKIE, ENGINEER_SESSION)
    return client


def test_the_original_url_is_the_public_https_address(monkeypatch, fake_core):
    monkeypatch.setenv("TRUSTED_PROXIES", "testclient")
    _client().get("/api/airsizer/config?x=1", headers=THROUGH_THE_PROXIES)
    assert fake_core.calls[-1].headers["x-original-url"] == (
        f"https://{PUBLIC}/api/airsizer/config?x=1")


def test_the_sign_in_comes_back_to_the_public_address(monkeypatch):
    """The whole point: Core's login_url carries the https:// page as next."""
    monkeypatch.setenv("TRUSTED_PROXIES", "testclient")
    response = _client(signed_in=False).get(
        "/hapext/upload", headers=THROUGH_THE_PROXIES, follow_redirects=False)
    assert response.status_code == 302
    query = parse_qs(urlparse(response.headers["location"]).query)
    assert query["next"] == [f"https://{PUBLIC}/hapext/upload"]


def test_an_untrusted_peer_s_forwarded_headers_are_ignored(monkeypatch, fake_core):
    """The control for the tests above: the same headers from a peer outside
    TRUSTED_PROXIES change nothing — neither the scheme nor the host."""
    monkeypatch.setenv("TRUSTED_PROXIES", "10.231.2.0/24")
    _client().get("/api/airsizer/config?x=1", headers=THROUGH_THE_PROXIES)
    assert fake_core.calls[-1].headers["x-original-url"] == (
        "http://backend:8000/api/airsizer/config?x=1")


def test_nobody_is_trusted_when_nothing_is_configured(monkeypatch, fake_core):
    monkeypatch.delenv("TRUSTED_PROXIES", raising=False)
    _client().get("/api/airsizer/config", headers=THROUGH_THE_PROXIES)
    assert fake_core.calls[-1].headers["x-original-url"].startswith("http://backend:8000/")


@pytest.mark.parametrize("peer, trusted", [
    ("10.231.2.5", True),        # the nginx container, on maec_et_net
    ("10.231.2.254", True),
    ("10.231.1.7", False),       # MAEC One Core, on maec_core_net: never
    ("10.231.1.1", False),       # maec_core_net's gateway
    ("10.231.0.5", False),       # Core's private network
    ("172.30.57.3", False),      # the old stack's network
    ("127.0.0.1", False),
    ("203.0.113.7", False),
    ("not-an-address", False),
    (None, False),
])
def test_only_the_nginx_network_is_trusted(monkeypatch, peer, trusted):
    """The backend sits on Core's shared network too, where Core and later
    apps can reach it directly. They must not choose its scheme or host."""
    monkeypatch.setenv("TRUSTED_PROXIES", "10.231.2.0/24")
    assert proxy.trusts(peer) is trusted


def test_trusting_everyone_is_refused(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXIES", "10.231.2.0/24,*")
    with pytest.raises(proxy.ProxyConfigError):
        proxy.check()
    with pytest.raises(proxy.ProxyConfigError):
        with TestClient(app):
            pass


@pytest.mark.parametrize("hostile", [
    "evil.example/path", "user@evil.example", "evil example", "evil.example:99999999",
])
def test_a_malformed_forwarded_host_is_not_used(monkeypatch, fake_core, hostile):
    monkeypatch.setenv("TRUSTED_PROXIES", "testclient")
    _client().get("/api/airsizer/config",
                  headers={**THROUGH_THE_PROXIES, "X-Forwarded-Host": hostile})
    assert fake_core.calls[-1].headers["x-original-url"] == (
        "https://backend:8000/api/airsizer/config")


# ------------------------------------------------- the deployment's wiring
def _nginx_api_block() -> str:
    text = (ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")
    return text[text.index("location /api/"):]


def test_nginx_passes_caddy_s_scheme_through_unchanged():
    """nginx's own $scheme is always http behind Caddy; sending it would
    make the app believe it is on http://."""
    block = _nginx_api_block()
    assert re.search(r"proxy_set_header\s+X-Forwarded-Proto\s+\$http_x_forwarded_proto;", block)
    assert not re.search(r"proxy_set_header\s+X-Forwarded-Proto\s+\$scheme", block)


def test_nginx_passes_caddy_s_host_through_unchanged():
    block = _nginx_api_block()
    assert re.search(r"proxy_set_header\s+X-Forwarded-Host\s+\$http_x_forwarded_host;", block)


def test_uvicorn_leaves_proxy_headers_to_the_app():
    """uvicorn's own --proxy-headers would replace the peer address before
    the app could check it, so it is switched off and the app's list rules."""
    entrypoint = (ROOT / "backend" / "docker-entrypoint.sh").read_text(encoding="utf-8")
    assert "--no-proxy-headers" in entrypoint
    assert "--proxy-headers" not in entrypoint.replace("--no-proxy-headers", "")
    assert "--forwarded-allow-ips" not in entrypoint


def test_the_trusted_range_is_exactly_the_nginx_network():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    trusted = re.search(r'TRUSTED_PROXIES:\s*"([^"]+)"', compose).group(1)
    subnet = re.search(r'subnet:\s*"([^"]+)"', compose).group(1)
    assert trusted == subnet == "${ET_NET_SUBNET:-10.231.2.0/24}"
