"""The real address behind the front door: Caddy -> nginx -> uvicorn.

Behind the proxies this process sees plain http and an internal host. Core
builds the sign-in's `next` from the X-Original-URL the gate sends, and only
follows a `next` on an app's own https:// address, so that URL has to be the
one the browser used.

The "proxy" here is uvicorn's own ProxyHeadersMiddleware — the code that
`--proxy-headers --forwarded-allow-ips` switches on — wrapped around the app
with the test client as the trusted (or untrusted) peer.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from backend.main import app

from conftest import ENGINEER_SESSION, SESSION_COOKIE

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = "engineeringtools.mirageaec.com"

# What nginx sends on, having received Caddy's request: the internal hop is
# plain http to the backend container, and Caddy's headers ride along.
THROUGH_THE_PROXIES = {
    "Host": "backend:8000",
    "X-Forwarded-Proto": "https",
    "X-Forwarded-Host": PUBLIC,
    "X-Forwarded-For": "203.0.113.7",
}


def _behind(trusted: str, *, signed_in: bool = True) -> TestClient:
    """The app as uvicorn runs it with --proxy-headers, trusting `trusted`.
    TestClient's peer address is the literal "testclient"."""
    client = TestClient(ProxyHeadersMiddleware(app, trusted_hosts=trusted))
    if signed_in:
        client.cookies.set(SESSION_COOKIE, ENGINEER_SESSION)
    return client


def test_the_original_url_is_the_public_https_address(monkeypatch, fake_core):
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "172.30.57.0/24")
    client = _behind("testclient")
    client.get("/api/airsizer/config?x=1", headers=THROUGH_THE_PROXIES)
    assert fake_core.calls[-1].headers["x-original-url"] == (
        f"https://{PUBLIC}/api/airsizer/config?x=1")


def test_the_sign_in_comes_back_to_the_public_address(monkeypatch):
    """The whole point: Core's login_url carries the https:// page as next."""
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "172.30.57.0/24")
    client = _behind("testclient", signed_in=False)
    response = client.get("/hapext/upload", headers=THROUGH_THE_PROXIES,
                          follow_redirects=False)
    assert response.status_code == 302
    query = parse_qs(urlparse(response.headers["location"]).query)
    assert query["next"] == [f"https://{PUBLIC}/hapext/upload"]


def test_an_untrusted_peer_s_forwarded_headers_are_ignored(monkeypatch, fake_core):
    """The control for the test above: the same headers from a peer uvicorn
    does not trust, and with no proxy configured, change nothing."""
    monkeypatch.delenv("FORWARDED_ALLOW_IPS", raising=False)
    client = _behind("10.9.9.9")
    client.get("/api/airsizer/config?x=1", headers=THROUGH_THE_PROXIES)
    assert fake_core.calls[-1].headers["x-original-url"] == (
        "http://backend:8000/api/airsizer/config?x=1")


@pytest.mark.parametrize("hostile", [
    "evil.example/path", "user@evil.example", "evil example", "evil.example:99999999",
])
def test_a_malformed_forwarded_host_is_not_used(monkeypatch, fake_core, hostile):
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "172.30.57.0/24")
    client = _behind("testclient")
    client.get("/api/airsizer/config",
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


def test_uvicorn_trusts_exactly_the_docker_network():
    entrypoint = (ROOT / "backend" / "docker-entrypoint.sh").read_text(encoding="utf-8")
    assert "--proxy-headers" in entrypoint
    assert '--forwarded-allow-ips "${FORWARDED_ALLOW_IPS}"' in entrypoint

    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    trusted = re.search(r'FORWARDED_ALLOW_IPS:\s*"([^"]+)"', compose).group(1)
    subnet = re.search(r"subnet:\s*(\S+)", compose).group(1)
    assert trusted == subnet
