"""Response headers.

These gate nobody: a signed-in user cannot tell they are here. They bound
what a browser will do with a page we served, so that a page carrying
something it should not do less damage.
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import CSP, SECURITY_HEADERS, app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.parametrize("header", list(SECURITY_HEADERS))
def test_every_response_carries_the_headers(client, header):
    """Including the ones a stranger gets, which is when they matter most."""
    assert header in client.get("/").headers
    assert header in client.get("/api/health").headers
    # Was a 401 — the gate refused it and the headers rode along on the
    # refusal, which is exactly when they matter most. With no gate this is
    # a 200. The assertion is unchanged; only the reason it is interesting
    # has gone, and it comes back with the token guard.
    assert header in client.get("/api/airsizer/config").headers


def test_scripts_may_only_come_from_us():
    """The CDN snippets that circulate for 'disabling devtools' are exactly
    what this refuses to load."""
    assert "script-src 'self'" in CSP
    assert "default-src 'self'" in CSP


def test_the_two_concessions_are_the_ones_the_app_needs():
    # React writes style="" attributes out of JSX
    assert "style-src 'self' 'unsafe-inline'" in CSP
    # the Project Details logo preview reads the file via createObjectURL
    assert "img-src 'self' data: blob:" in CSP


def test_other_sites_cannot_frame_the_sign_in_form():
    assert "frame-ancestors 'self'" in CSP
    assert SECURITY_HEADERS["X-Frame-Options"] == "SAMEORIGIN"


def test_our_own_platform_may_still_frame_us():
    """MAEC One may come to embed its modules; 'none' would forbid that."""
    assert "frame-ancestors 'none'" not in CSP


def test_hsts_only_once_deployed(monkeypatch, client):
    """Asserting it locally would pin a developer's browser to https://."""
    monkeypatch.delenv("RENDER", raising=False)
    assert "Strict-Transport-Security" not in TestClient(app).get("/").headers
    monkeypatch.setenv("RENDER", "true")
    assert "Strict-Transport-Security" in TestClient(app).get("/").headers


def test_headers_do_not_gate_anything(client):
    """The point of the whole file: nothing here changes who gets in.

    It used to make the last call as a signed-in engineer, because a
    stranger would have been refused by the gate rather than by anything in
    this file. There is no gate now, so a plain client reaches it — and the
    assertion means what it always meant: these headers let the request
    through.
    """
    assert client.get("/api/health").status_code == 200
    assert client.get("/").status_code == 200
    assert client.get("/api/airsizer/config").status_code == 200
