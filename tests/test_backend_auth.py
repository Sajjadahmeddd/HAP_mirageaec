"""What guards Engineering Tools: the gate, and the map from route to permission.

Everything runs against the fake Core in conftest.py, swapped in as the gate's
HTTP transport. Nothing leaves the process.

Where a test shows a refusal, it also shows the same request let through once
the one thing that differs is put right — a refusal from a test that could
never have answered otherwise proves nothing.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.maec_auth import config, gate, guard
from backend.main import FRONTEND_DIST, app

from conftest import (
    APP_KEY, CORE_PUBLIC_URL, CORE_URL, ENGINEER_SESSION, GATE_SECRET, SESSION_COOKIE,
)

# Every product route that must never answer a stranger.
GUARDED = [
    ("GET", "/api/airsizer/config"),
    ("GET", "/api/airsizer/diagram/square"),
    ("POST", "/api/airsizer/load"),
    ("POST", "/api/airsizer/load-rows"),
    ("POST", "/api/airsizer/size"),
    ("POST", "/api/airsizer/export"),
    ("POST", "/api/hapext/inspect"),
    ("POST", "/api/hapext/inspect-schedule"),
    ("POST", "/api/hapext/convert"),
    ("POST", "/api/hapext/download"),
    ("POST", "/api/hapext/change-request"),
    ("POST", "/api/rebadge/validate"),
    ("POST", "/api/rebadge/preview"),
    ("POST", "/api/rebadge/apply"),
]

DOCS = ["/docs", "/redoc", "/openapi.json"]

needs_bundle = pytest.mark.skipif(not FRONTEND_DIST.is_dir(), reason="frontend/dist not built")


# ================================================================ no cookie
@pytest.mark.parametrize("method,path", GUARDED)
def test_an_api_call_without_a_cookie_is_401_with_the_login_url(app_client, method, path):
    """The frontend handles it: it sends the window to login_url. The API itself
    never redirects — it is called by fetch."""
    response = app_client.request(method, path, follow_redirects=False)
    assert response.status_code == 401
    assert "location" not in response.headers
    body = response.json()
    assert body["reason"] == "not_signed_in"
    assert body["login_url"].startswith(f"{CORE_PUBLIC_URL}/?next=")


def test_a_page_without_a_cookie_is_sent_to_sign_in_and_back(app_client):
    """302 to Core's sign-in, carrying the exact page asked for as `next`."""
    response = app_client.get("/hapext/upload?x=1", follow_redirects=False)
    assert response.status_code == 302
    target = urlparse(response.headers["location"])
    assert f"{target.scheme}://{target.netloc}" == CORE_PUBLIC_URL
    assert parse_qs(target.query)["next"] == ["http://testserver/hapext/upload?x=1"]


def test_the_same_page_opens_with_a_valid_cookie(engineer_client):
    """The control for the test above: same page, a session, no redirect."""
    response = engineer_client.get("/hapext/upload?x=1", follow_redirects=False)
    assert response.status_code != 302
    assert "location" not in response.headers


def test_a_session_core_does_not_know_is_not_signed_in(app_client, engineer_client):
    app_client.cookies.set(SESSION_COOKIE, "made-up-session-id")
    assert app_client.get("/api/airsizer/config").status_code == 401
    assert engineer_client.get("/api/airsizer/config").status_code == 200


@pytest.mark.parametrize("path", DOCS)
def test_the_api_docs_need_a_signed_in_person(app_client, engineer_client, path):
    """They enumerate every route. A session is the whole requirement."""
    assert app_client.get(path, follow_redirects=False).status_code == 302
    assert engineer_client.get(path).status_code == 200


def test_me_says_401_to_a_stranger(app_client):
    response = app_client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["login_url"]


# ============================================================ a valid check
def test_a_valid_check_lets_the_request_through(engineer_client):
    assert engineer_client.get("/api/airsizer/config").status_code == 200


def test_core_s_answer_is_on_request_state(engineer_client):
    """What /api/auth/me reports is what Core said, via request.state.maec."""
    body = engineer_client.get("/api/auth/me").json()
    assert body["authenticated"] is True
    assert body["email"] == "engineer@mirageaec.com"
    assert body["name"] == "Test Engineer"
    assert body["nav_hidden"] == []
    assert body["core_url"] == CORE_URL
    assert body["modules"] == {"hapext": True, "airsizer": True,
                               "hapaudit": True, "rebadge": True}


def test_the_gate_forwards_what_core_needs(engineer_client, fake_core):
    """The raw Cookie, the full original URL, the method, the Origin, and this
    app's key and secret — to Core's check URL, with a three-second timeout."""
    engineer_client.post("/api/hapext/inspect?a=b",
                         headers={"Origin": "http://et.maec.local:8080"})
    call = fake_core.calls[-1]
    assert str(call.url) == f"{CORE_URL}/api/gate/check"
    assert call.method == "GET"
    assert f"{SESSION_COOKIE}={ENGINEER_SESSION}" in call.headers["cookie"]
    assert call.headers["x-original-url"] == "http://testserver/api/hapext/inspect?a=b"
    assert call.headers["x-original-method"] == "POST"
    assert call.headers["x-original-origin"] == "http://et.maec.local:8080"
    assert call.headers["x-maec-app"] == APP_KEY
    assert call.headers["x-maec-gate-secret"] == GATE_SECRET
    assert call.extensions["timeout"] == {"connect": 3.0, "read": 3.0,
                                          "write": 3.0, "pool": 3.0}


def test_the_gate_secret_never_reaches_the_browser(engineer_client, app_client):
    for response in (engineer_client.get("/api/auth/me"),
                     engineer_client.get("/"),
                     app_client.get("/api/airsizer/config"),
                     app_client.get("/", follow_redirects=False)):
        assert GATE_SECRET not in response.text
        assert GATE_SECRET not in str(response.headers)


def test_nothing_is_cached_a_sign_out_bites_on_the_next_request(engineer_client, fake_core):
    """Core is asked every time, so the moment Core forgets the session the
    very next request here is refused."""
    assert engineer_client.get("/api/airsizer/config").status_code == 200
    del fake_core.sessions[ENGINEER_SESSION]
    assert engineer_client.get("/api/airsizer/config").status_code == 401


# =========================================================== no permission
def test_a_missing_permission_is_403(engineer_client, fake_core):
    engineer = fake_core.engineer()
    engineer["permissions"].remove("engineering:hapext:convert")
    assert engineer_client.post("/api/hapext/convert").status_code == 403
    # control: the same person still reaches a route whose key they hold
    assert engineer_client.post("/api/hapext/inspect").status_code not in (401, 403)


def test_a_view_only_person_can_look_but_not_produce(engineer_client, fake_core):
    fake_core.engineer()["permissions"] = ["engineering:hapext:view"]
    assert engineer_client.post("/api/hapext/inspect").status_code not in (401, 403)
    assert engineer_client.post("/api/hapext/convert").status_code == 403
    assert engineer_client.post("/api/hapext/download").status_code == 403
    assert engineer_client.get("/api/airsizer/config").status_code == 403


def test_no_seat_is_403_with_core_s_reason_for_the_api(engineer_client, fake_core):
    fake_core.refused[ENGINEER_SESSION] = (403, "no_access")
    response = engineer_client.get("/api/airsizer/config")
    assert response.status_code == 403
    assert response.json()["reason"] == "no_access"
    assert response.json()["login_url"]


def test_no_seat_is_a_page_saying_so_with_a_way_back(engineer_client, fake_core):
    fake_core.refused[ENGINEER_SESSION] = (403, "no_access")
    response = engineer_client.get("/", follow_redirects=False)
    assert response.status_code == 403
    assert "text/html" in response.headers["content-type"]
    assert "does not have access to Engineering Tools" in response.text
    assert f'href="{CORE_URL}/"' in response.text
    assert "location" not in response.headers


def test_every_product_route_names_a_permission():
    """Structural: a route added to a router without a map entry is refused by
    the guard's default. That is the safe direction, but a route should be
    closed on purpose, not because nobody remembered — so this fails first."""
    unmapped = []
    for route in app.routes:
        path, methods = getattr(route, "path", ""), getattr(route, "methods", set())
        if not path.startswith("/api/") or path in guard.PUBLIC or path in guard.OPEN:
            continue
        concrete = path.replace("{key}", "square")
        for method in methods - {"HEAD", "OPTIONS"}:
            if guard.permission_for(method, concrete) is None:
                unmapped.append(f"{method} {path}")
    assert not unmapped, unmapped


def _ungated_status(monkeypatch, client, method, path):
    """What the app itself answers with the gate switched off - which is what
    the live app answers, its routing being the same code."""
    async def let_through(request):
        return None
    with monkeypatch.context() as m:
        m.setattr(gate, "inspect", let_through)
        return client.request(method, path).status_code


@pytest.mark.parametrize("method,path", [
    ("POST", "/api/hapext/not-a-route"),   # no such path
    ("GET", "/api/no-such-route"),
    ("GET", "/api/hapext/convert"),        # a POST-only route
    ("PUT", "/api/hapext/convert"),
    ("DELETE", "/api/rebadge/apply"),
    ("HEAD", "/api/airsizer/config"),      # FastAPI does not add HEAD to GET routes
    ("OPTIONS", "/api/airsizer/config"),
])
def test_no_route_gets_the_app_s_own_answer_not_a_403(monkeypatch, engineer_client, method, path):
    """For a signed-in person, a wrong method on a real path and a path that
    does not exist get exactly the app's answer (405 / 404), as on live -
    never the gate's 403. Nothing is served: there is no route to serve."""
    expected = _ungated_status(monkeypatch, engineer_client, method, path)
    assert expected in (404, 405)
    assert engineer_client.request(method, path).status_code == expected


def test_a_real_route_with_no_permission_mapped_is_still_refused(engineer_client):
    """Default closed where it matters: a product route that exists but was
    never given a permission is refused, not served."""
    from backend.main import app
    app.router.add_api_route("/api/hapext/unmapped-probe", lambda: {"served": True},
                             methods=["GET"])
    try:
        response = engineer_client.get("/api/hapext/unmapped-probe")
        assert response.status_code == 403
        assert "served" not in response.text
    finally:
        app.router.routes[:] = [r for r in app.router.routes
                                if getattr(r, "path", "") != "/api/hapext/unmapped-probe"]


def test_gated_answers_say_they_depend_on_the_cookie(engineer_client, app_client):
    """As live's session middleware does: Vary: Cookie on every response
    whose answer depended on it, refusals included - and not on health."""
    assert "Cookie" in engineer_client.get("/api/airsizer/config").headers["vary"]
    assert "Cookie" in app_client.get("/api/airsizer/config").headers["vary"]
    assert "Cookie" in engineer_client.post("/api/hapext/not-a-route").headers["vary"]
    assert "Cookie" not in app_client.get("/api/health").headers.get("vary", "")


# ================================================================ tab hiding
def test_nav_hidden_takes_the_tab_away_but_the_api_still_answers(engineer_client, fake_core):
    """Decluttering, not a boundary: the permission still holds."""
    fake_core.engineer()["nav_hidden"] = ["rebadge"]
    body = engineer_client.get("/api/auth/me").json()
    assert body["nav_hidden"] == ["rebadge"]
    assert body["modules"]["rebadge"] is False
    assert body["modules"]["hapext"] is True
    assert engineer_client.post("/api/rebadge/validate").status_code not in (401, 403)


def test_no_view_permission_takes_the_tab_away_too(engineer_client, fake_core):
    engineer = fake_core.engineer()
    engineer["permissions"] = [p for p in engineer["permissions"]
                               if not p.startswith("engineering:rebadge:")]
    assert engineer_client.get("/api/auth/me").json()["modules"]["rebadge"] is False
    assert engineer_client.post("/api/rebadge/validate").status_code == 403


# ================================================================= Core down
@pytest.mark.parametrize("method,path", [("GET", "/api/airsizer/config"),
                                         ("POST", "/api/hapext/convert"),
                                         ("GET", "/api/auth/me")])
def test_core_down_is_503_never_a_pass(engineer_client, fake_core, method, path):
    fake_core.down = True
    response = engineer_client.request(method, path)
    assert response.status_code == 503
    assert response.json()["detail"] == "MAEC One is unavailable"


def test_core_down_is_a_503_page_for_a_page(engineer_client, fake_core):
    fake_core.down = True
    response = engineer_client.get("/", follow_redirects=False)
    assert response.status_code == 503
    assert "MAEC One is unavailable" in response.text


def test_core_answering_with_an_error_is_503(engineer_client, fake_core):
    assert engineer_client.get("/api/airsizer/config").status_code == 200   # control
    fake_core.status = 500
    assert engineer_client.get("/api/airsizer/config").status_code == 503


def test_core_too_slow_is_503(engineer_client, fake_core, monkeypatch):
    def slow(request):
        raise httpx.ReadTimeout("no answer within 3 s", request=request)
    monkeypatch.setattr(gate, "transport", httpx.MockTransport(slow))
    gate.reset_client()
    assert engineer_client.get("/api/airsizer/config").status_code == 503


def test_a_wrong_gate_secret_is_refused(engineer_client, monkeypatch):
    """Core answers 403 bad_app; nobody gets in, signed in or not."""
    monkeypatch.setenv("MAEC_GATE_SECRET", "not-the-secret-core-holds-xxxxxxxx")
    response = engineer_client.get("/api/airsizer/config")
    assert response.status_code == 403
    assert response.json()["reason"] == "bad_app"


def test_missing_settings_refuse_every_gated_request(engineer_client, monkeypatch):
    monkeypatch.delenv("MAEC_GATE_SECRET")
    assert engineer_client.get("/api/airsizer/config").status_code == 503


# ================================================================== startup
@pytest.mark.parametrize("name", config.REQUIRED)
def test_the_service_refuses_to_start_without_a_setting(monkeypatch, name):
    monkeypatch.delenv(name)
    with pytest.raises(config.ConfigError, match=name):
        with TestClient(app):
            pass


def test_the_service_starts_with_all_three(monkeypatch):
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200


# ============================================================ always public
def test_health_is_public_and_needs_no_core(app_client, fake_core):
    """Render probes it without a session, and it must answer when Core is down."""
    fake_core.down = True
    response = app_client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["auth"] == "gate"
    assert fake_core.calls == []


@needs_bundle
def test_the_bundle_s_static_files_do_not_ask_core(app_client, fake_core):
    assets = sorted((FRONTEND_DIST / "assets").iterdir())
    assert app_client.get(f"/assets/{assets[0].name}").status_code == 200
    assert app_client.get("/favicon.png").status_code == 200
    assert fake_core.calls == []


def test_the_security_headers_ride_on_a_refusal(app_client):
    """security_headers is outermost, so the gate's refusals carry the CSP too."""
    refused = app_client.get("/api/airsizer/config")
    assert refused.status_code == 401
    assert "Content-Security-Policy" in refused.headers
    redirected = app_client.get("/", follow_redirects=False)
    assert redirected.status_code == 302
    assert "Content-Security-Policy" in redirected.headers


# ================================================================ catch-all
@needs_bundle
# Encoded forms only. A literal "/../../backend/main.py" is not tested here
# because it cannot be: httpx collapses the dot segments on the client and
# sends "/backend/main.py", which never reached the hole even before the fix —
# that variant passed against the vulnerable code, so it proved nothing. The
# encoded forms arrive with ".." intact, which is what curl --path-as-is or a
# raw socket sends, and each of them failed against the unfixed route.
@pytest.mark.parametrize("path", [
    "/..%2f..%2fbackend%2fmain.py",
    "/%2e%2e/%2e%2e/backend/main.py",
    "/%2e%2e%2f%2e%2e%2fbackend%2fmain.py",
])
def test_the_catch_all_does_not_serve_files_outside_the_bundle(engineer_client, path):
    """`dist / "../../backend/main.py"` is a real file. The catch-all used to
    serve it. Whatever the encoding, the answer is the SPA's index."""
    index = (FRONTEND_DIST / "index.html").read_bytes()
    response = engineer_client.get(path)
    assert response.status_code == 200
    assert response.content == index
    assert b"FastAPI" not in response.content


# ================================================================== logging
def test_logging_is_configured_so_info_lines_are_not_dropped():
    """uvicorn leaves the root logger alone, so a refused permission (INFO)
    would go unheard. Carried over from main's sign-in log test."""
    import logging
    gate.configure_logging()
    assert gate.log.level == logging.INFO

    before = list(gate.log.handlers)
    gate.configure_logging()          # startup can run more than once
    assert gate.log.handlers == before


# ======================================================= public vs internal
def test_sign_out_points_at_core_s_public_address(engineer_client, monkeypatch):
    """In the container CORE_URL is Docker-internal (http://maec-core:8000),
    which no browser can open; links the browser follows use CORE_PUBLIC_URL."""
    monkeypatch.setenv("CORE_URL", "http://maec-core:8000")
    monkeypatch.setenv("CORE_PUBLIC_URL", "https://auth.mirageaec.com")
    assert engineer_client.get("/api/auth/me").json()["core_url"] == "https://auth.mirageaec.com"


def test_the_no_access_page_links_to_core_s_public_address(engineer_client, fake_core,
                                                           monkeypatch):
    monkeypatch.setenv("CORE_URL", "http://maec-core:8000")
    monkeypatch.setenv("CORE_PUBLIC_URL", "https://auth.mirageaec.com")
    fake_core.refused[ENGINEER_SESSION] = (403, "no_access")
    page = engineer_client.get("/", follow_redirects=False).text
    assert 'href="https://auth.mirageaec.com/"' in page
    assert "maec-core" not in page


def test_without_a_public_address_links_fall_back_to_core_url(engineer_client, monkeypatch):
    """One address serves both on a developer's machine."""
    monkeypatch.delenv("CORE_PUBLIC_URL", raising=False)
    assert engineer_client.get("/api/auth/me").json()["core_url"] == CORE_URL
