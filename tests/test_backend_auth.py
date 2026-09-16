"""What guards Engineering Tools.

This file spent one branch pinning the hole: live tests asserting every
product route answered a stranger, and skipped tests naming what the OIDC
client would have to restore. Their docstrings said to delete the first kind
the day authentication returned and not to relax them. That day is this one —
they are gone, replaced by the guarantees they were standing in for, and the
placeholders below them are now real tests.

Everything runs against a miniature Core defined in conftest.py: a keypair
generated for this run, a stubbed JWKS serving its public half, a stubbed
token endpoint. Core's real key is never involved and nothing leaves the
process. Sign-ins go through the actual /auth/login → /auth/callback path.
"""

from __future__ import annotations

import types
from urllib.parse import urlparse

import jwt
import pytest
from fastapi.testclient import TestClient

from backend.maec_auth import config, guard, session, verify
from backend.main import FRONTEND_DIST, app

from conftest import CLIENT_SECRET, ISSUER, KID, ROLE_ID, core_claims

# Every product route that must never answer a stranger. The first twelve are
# the list this file inherited. The last two were missing from it: preview runs
# a real rebadge and returns a picture of it, apply writes the whole set.
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


def _no_session_cookie(client: TestClient) -> bool:
    return config.SESSION_COOKIE not in client.cookies


# ================================================================ strangers
@pytest.mark.parametrize("method,path", GUARDED)
def test_every_product_route_refuses_a_stranger(app_client, method, path):
    """The requirement this file exists for. It did not stop being true when
    Core moved out; for one branch it stopped being enforced."""
    response = app_client.request(method, path)
    assert response.status_code == 401
    assert response.json()["detail"] == "Sign in required."


@pytest.mark.parametrize("method,path", GUARDED)
def test_the_api_refuses_rather_than_redirects(app_client, method, path):
    """A 401, never a 302 to Core. The API is called by fetch, and a redirect
    to an HTML sign-in page is nothing fetch can use — the browser decides to
    leave the page, through /auth/login, the one place that redirects."""
    response = app_client.request(method, path, follow_redirects=False)
    assert "location" not in response.headers


@pytest.mark.parametrize("path", DOCS)
def test_the_api_docs_are_not_readable_by_a_stranger(app_client, path):
    """They enumerate every route and its schema. Decided: behind the gate."""
    assert app_client.get(path).status_code == 401


@pytest.mark.parametrize("path", DOCS)
def test_the_api_docs_open_once_signed_in(engineer_client, path):
    """A session is the whole requirement — no permission. Reading the schema
    of a route you cannot call teaches nothing the UI would not."""
    assert engineer_client.get(path).status_code == 200


def test_health_is_public_and_says_how_it_is_guarded(app_client):
    """Render probes it without a session, and it must keep answering when
    Core is down. It said "none" while this branch had no gate."""
    response = app_client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["auth"] == "oidc"


def test_me_says_401_to_a_stranger(app_client):
    """The frontend's signal to visit /auth/login."""
    assert app_client.get("/api/auth/me").status_code == 401


def test_the_spa_shell_is_still_served(app_client):
    """The bundle loads for anybody — it has to, to discover it is signed out."""
    assert app_client.get("/").status_code == 200


def test_the_security_headers_ride_on_a_refusal(app_client):
    """security_headers is outermost, so the guard's 401 carries the CSP too."""
    refused = app_client.get("/api/airsizer/config")
    assert refused.status_code == 401
    assert "Content-Security-Policy" in refused.headers


def test_every_product_route_names_a_permission():
    """Structural: a route added to a router without a map entry is refused by
    the guard's default. That is the safe direction, but a route should be
    closed on purpose, not because nobody remembered — so this fails first."""
    unmapped = []
    for route in app.routes:
        path, methods = getattr(route, "path", ""), getattr(route, "methods", set())
        if not path.startswith("/api/") or path in guard.PUBLIC:
            continue
        if path.startswith(guard.OPEN_PREFIXES):
            continue
        concrete = path.replace("{key}", "square")
        for method in methods - {"HEAD", "OPTIONS"}:
            if guard.permission_for(method, concrete) is None:
                unmapped.append(f"{method} {path}")
    assert not unmapped, unmapped


def test_an_unmapped_api_route_is_refused_not_served(engineer_client):
    assert engineer_client.post("/api/hapext/not-a-route").status_code == 403


# =================================================================== tokens
def test_a_forged_token_is_rejected(mint, forger_key, app_client, sign_in):
    """Signed with a key Core does not publish, under Core's own kid. Refused
    at verification — and so no session exists, and the API stays shut."""
    forged = mint(core_claims(), key=forger_key)
    with pytest.raises(verify.SignatureRejected):
        verify.verify(forged)

    callback, _ = sign_in(app_client, token=forged)
    assert callback.status_code == 400
    assert _no_session_cookie(app_client)
    assert app_client.get("/api/airsizer/config").status_code == 401


def test_an_altered_token_is_rejected(mint):
    """A genuine token with one claim edited: the signature no longer holds."""
    header, payload, signature = mint(core_claims()).split(".")
    raw = jwt.utils.base64url_decode(payload)
    assert b'"entitled":true' in raw
    edited = jwt.utils.base64url_encode(
        raw.replace(b'"entitled":true', b'"entitled":false')).decode()
    tampered = ".".join([header, edited, signature])
    with pytest.raises(verify.SignatureRejected):
        verify.verify(tampered)


def test_a_token_for_another_audience_is_rejected(mint, app_client, sign_in):
    """Core really did sign it — for another application. `aud` is what keeps
    eight applications on one issuer apart."""
    for_finance = mint(core_claims(aud="finance"))
    with pytest.raises(verify.ClaimsRejected):
        verify.verify(for_finance)

    callback, _ = sign_in(app_client, token=for_finance)
    assert callback.status_code == 400
    assert _no_session_cookie(app_client)


def test_a_token_from_another_issuer_is_rejected(mint):
    with pytest.raises(verify.ClaimsRejected):
        verify.verify(mint(core_claims(iss="http://some-other-core.test")))


def test_an_expired_token_is_rejected(mint):
    """Past exp by more than the 30s leeway."""
    import time
    stale = mint(core_claims(iat=int(time.time()) - 3600, exp=int(time.time()) - 120))
    with pytest.raises(verify.ClaimsRejected):
        verify.verify(stale)


@pytest.mark.parametrize("algorithm", ["none", "HS256"])
def test_an_algorithm_swap_is_rejected(signing_key, algorithm):
    """`alg: none`, and HS256 signed with the public key as the secret — the
    two classic ways to make an RS256 verifier accept something it should not."""
    from cryptography.hazmat.primitives import serialization
    claims = core_claims()
    if algorithm == "none":
        token = jwt.encode(claims, None, algorithm="none", headers={"kid": KID})
    else:
        public_pem = signing_key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        header = jwt.utils.base64url_encode(
            b'{"alg":"HS256","typ":"JWT","kid":"%s"}' % KID.encode()).decode()
        body = jwt.utils.base64url_encode(
            jwt.api_jws.json.dumps(claims, separators=(",", ":")).encode()).decode()
        import hashlib
        import hmac
        mac = hmac.new(public_pem, f"{header}.{body}".encode(), hashlib.sha256).digest()
        token = f"{header}.{body}.{jwt.utils.base64url_encode(mac).decode()}"
    with pytest.raises(verify.TokenRejected):
        verify.verify(token)


def test_keys_come_only_from_the_configured_issuer(mint, jwks_fetches):
    """A token naming its own key server — jku, or an iss pointing elsewhere —
    must not make this service fetch from it. That would be an SSRF against
    which a forgery verifies perfectly."""
    hostile = jwt.encode(core_claims(iss="http://attacker.test"),
                         "irrelevant", algorithm="HS256",
                         headers={"kid": "attacker", "jku": "http://attacker.test/jwks"})
    with pytest.raises(verify.TokenRejected):
        verify.verify(hostile)
    verify.verify(mint(core_claims()))
    assert jwks_fetches, "expected at least one key fetch"
    assert {urlparse(url).netloc for url in jwks_fetches} == {urlparse(ISSUER).netloc}


def test_an_unknown_kid_refetches_once_then_refuses(mint, signing_key, jwks_fetches):
    """Core rotates keys, so a miss is first read as a stale cache. One refetch,
    then an answer — invented kids must not make this service hammer Core."""
    verify.verify(mint(core_claims()))                 # warm the cache
    before = len(jwks_fetches)
    with pytest.raises(verify.KeyUnknown):
        verify.verify(mint(core_claims(), kid="rotated-away"))
    assert len(jwks_fetches) - before == 1


def test_keys_are_cached_between_verifications(mint, jwks_fetches):
    for _ in range(5):
        verify.verify(mint(core_claims()))
    assert len(jwks_fetches) == 1


# ================================================================= callback
def test_a_callback_without_the_state_cookie_is_refused_before_any_exchange(
        monkeypatch, app_client):
    """No state cookie means this browser never started a sign-in here. The
    code is not spent: nothing is posted to Core at all."""
    import httpx
    posted = []
    monkeypatch.setattr(httpx, "post", lambda *a, **k: posted.append(a))
    response = app_client.get("/auth/callback", params={"code": "c", "state": "s"},
                              follow_redirects=False)
    assert response.status_code == 400
    assert posted == []
    assert _no_session_cookie(app_client)


def test_a_callback_with_the_wrong_state_is_refused_before_any_exchange(app_client, sign_in):
    callback, exchanges = sign_in(app_client, state="not-the-state-we-issued")
    assert callback.status_code == 400
    assert exchanges == []
    assert _no_session_cookie(app_client)


def test_a_token_minted_for_another_sign_in_is_refused(app_client, sign_in):
    """A genuine, unexpired token carrying some other flow's nonce — a replay."""
    callback, _ = sign_in(app_client, claims={"nonce": "from-an-earlier-sign-in"})
    assert callback.status_code == 400
    assert _no_session_cookie(app_client)


def test_core_refusing_authorization_shows_a_page_not_a_redirect(app_client, sign_in):
    """Core redirects back with ?error= when a person is not entitled. The
    callback must not bounce back to /authorize — that is a loop."""
    launched = app_client.get("/auth/login", follow_redirects=False)
    from urllib.parse import parse_qs
    state = parse_qs(urlparse(launched.headers["location"]).query)["state"][0]
    response = app_client.get("/auth/callback",
                              params={"error": "access_denied", "state": state},
                              follow_redirects=False)
    assert response.status_code == 400
    assert "location" not in response.headers
    assert _no_session_cookie(app_client)


def test_login_redirects_to_the_configured_authorize_endpoint(app_client):
    launched = app_client.get("/auth/login", follow_redirects=False)
    target = urlparse(launched.headers["location"])
    assert f"{target.scheme}://{target.netloc}{target.path}" == f"{ISSUER}/oauth/authorize"
    from urllib.parse import parse_qs
    query = parse_qs(target.query)
    assert query["response_type"] == ["code"]
    assert query["client_id"] and query["redirect_uri"] and query["state"] and query["nonce"]


def test_the_client_secret_goes_only_server_to_server(app_client, sign_in):
    """It is in the body of the call to Core's token endpoint — and nowhere a
    browser could see it."""
    launched = app_client.get("/auth/login", follow_redirects=False)
    assert CLIENT_SECRET not in launched.headers["location"]

    callback, exchanges = sign_in(app_client)
    assert exchanges[0][0] == f"{ISSUER}/oauth/token"
    assert exchanges[0][1]["client_secret"] == CLIENT_SECRET
    assert exchanges[0][1]["grant_type"] == "authorization_code"
    for exposed in (callback.text, str(callback.headers), str(dict(app_client.cookies)),
                    app_client.get("/api/auth/me").text):
        assert CLIENT_SECRET not in exposed


# ================================================================== session
def test_the_session_cookie_carries_no_token_and_is_host_only(app_client, sign_in, mint):
    callback, _ = sign_in(app_client)
    assert callback.status_code == 302 and callback.headers["location"] == "/"

    set_cookies = callback.headers.get_list("set-cookie")
    ours = [c for c in set_cookies if c.startswith(f"{config.SESSION_COOKIE}=")]
    assert len(ours) == 1
    attributes = ours[0].lower()
    assert "httponly" in attributes
    assert "samesite=lax" in attributes
    assert "domain=" not in attributes                 # host-only
    assert not any(c.startswith("maec_session=") for c in set_cookies)

    value = app_client.cookies[config.SESSION_COOKIE]
    assert len(value) < 200                   # an id, not a ~7 kB token
    assert value.count(".") < 2               # a signed id has one dot; a JWT has two
    assert "engineer@mirageaec.com" not in value


def test_me_reports_the_person_and_never_the_token(engineer_client):
    body = engineer_client.get("/api/auth/me").json()
    assert body["authenticated"] is True
    assert body["email"] == "engineer@mirageaec.com"
    assert "token" not in body and "access_token" not in body
    assert body["modules"] == {"hapext": True, "airsizer": True,
                               "hapaudit": True, "rebadge": True}


def test_signing_in_opens_the_product_routes(engineer_client):
    assert engineer_client.get("/api/airsizer/config").status_code == 200


def test_a_session_does_not_leak_between_clients(engineer_client):
    """Carried over unchanged. One browser's credentials never answer for
    another's, whatever the credential is made of."""
    stranger = TestClient(app)
    assert engineer_client.get("/api/airsizer/config").status_code == 200
    assert stranger.get("/api/airsizer/config").status_code == 401


def test_a_session_cookie_this_service_did_not_sign_is_ignored(app_client):
    app_client.cookies.set(config.SESSION_COOKIE, "made-up-session-id")
    assert app_client.get("/api/airsizer/config").status_code == 401


def test_a_suspended_account_loses_access_within_the_token_lifetime(
        monkeypatch, engineer_client):
    """The number the placeholder asked for: fifteen minutes (Core #16).

    This service cannot see a suspension or a revoked seat — it has no user
    row to read. What it guarantees is that a session never outlives the token
    it was built from, so the next re-authorization, at most fifteen minutes
    later, asks Core again and Core refuses. The session is live one second
    before the token's exp and gone one second after it.
    """
    live = session.current(types.SimpleNamespace(cookies=engineer_client.cookies))
    assert live is not None
    lifetime = live.expires_at - live.claims["iat"]
    assert lifetime == 15 * 60

    clock = types.SimpleNamespace(time=lambda: live.expires_at - 1)
    monkeypatch.setattr(session, "time", clock)
    assert engineer_client.get("/api/airsizer/config").status_code == 200

    clock.time = lambda: live.expires_at + 1
    assert engineer_client.get("/api/airsizer/config").status_code == 401
    assert engineer_client.get("/api/auth/me").status_code == 401


def test_signing_out_closes_the_routes_again(engineer_client):
    assert engineer_client.get("/api/airsizer/config").status_code == 200
    engineer_client.post("/api/auth/logout")
    assert engineer_client.get("/api/airsizer/config").status_code == 401


# ============================================================== enforcement
def test_a_person_without_a_seat_cannot_reach_the_product_api(app_client, sign_in):
    """Entitlement from a claim rather than a licence row. Signed in, refused."""
    callback, _ = sign_in(app_client, claims={"entitled": False})
    assert callback.status_code == 302
    for method, path in GUARDED:
        assert app_client.request(method, path).status_code == 403, path


def test_a_role_that_denies_convert_keeps_view(app_client, sign_in):
    permissions = {f"engineering:hapext:{a}": "allow" for a in ("view", "export")}
    permissions["engineering:hapext:convert"] = "deny"
    sign_in(app_client, claims={"role_permissions": {ROLE_ID: permissions}})
    assert app_client.post("/api/hapext/convert").status_code == 403
    assert app_client.post("/api/hapext/inspect").status_code not in (401, 403)


def test_no_access_is_the_boundary_and_takes_the_tab_away(app_client, sign_in):
    sign_in(app_client, claims={"tool_rules": [
        {"module_key": "rebadge", "role_id": ROLE_ID, "access_level": "no_access"}]})
    assert app_client.post("/api/rebadge/validate").status_code == 403
    assert app_client.get("/api/auth/me").json()["modules"]["rebadge"] is False
    assert app_client.post("/api/hapext/inspect").status_code not in (401, 403)


def test_hidden_takes_the_tab_away_but_the_api_still_answers(app_client, sign_in):
    """Decluttering, not a boundary — kept distinct from no_access on purpose."""
    sign_in(app_client, claims={"tool_rules": [
        {"module_key": "rebadge", "role_id": ROLE_ID, "access_level": "hidden"}]})
    assert app_client.get("/api/auth/me").json()["modules"]["rebadge"] is False
    assert app_client.post("/api/rebadge/validate").status_code not in (401, 403)


def test_a_view_tool_rule_leaves_look_but_not_produce(app_client, sign_in):
    sign_in(app_client, claims={"tool_rules": [
        {"module_key": "hapext", "role_id": ROLE_ID, "access_level": "view"}]})
    assert app_client.post("/api/hapext/inspect").status_code not in (401, 403)
    assert app_client.post("/api/hapext/convert").status_code == 403
    assert app_client.post("/api/hapext/download").status_code == 403
    assert app_client.get("/api/auth/me").json()["modules"]["hapext"] is True


# ================================================================ catch-all
@pytest.mark.skipif(not FRONTEND_DIST.is_dir(), reason="frontend/dist not built")
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
def test_the_catch_all_does_not_serve_files_outside_the_bundle(app_client, path):
    """`dist / "../../backend/main.py"` is a real file. The catch-all used to
    serve it. Whatever the encoding, the answer is the SPA's index."""
    index = (FRONTEND_DIST / "index.html").read_bytes()
    response = app_client.get(path)
    assert response.status_code == 200
    assert response.content == index
    assert b"FastAPI" not in response.content
