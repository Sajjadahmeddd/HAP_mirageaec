"""Fixtures for the backend tests: a Core that exists only in this process.

Engineering Tools trusts tokens MAEC One Core signs. These tests cannot use
Core's key and must not reach Core's host, so they stand one up in miniature:

  * an RSA keypair generated once per run, whose public half is served by a
    stubbed JWKS fetch — `httpx.get` inside verify.py is replaced, so nothing
    leaves the process;
  * a second keypair that Core never publishes, for forging;
  * `mint()`, which signs a claim set shaped exactly like Core's tokens;
  * a stubbed token endpoint, so a sign-in runs the real /auth/login →
    /auth/callback path — state, nonce, exchange, verification, session —
    rather than planting a session behind the app's back.

`app_client` is a stranger. `engineer_client` has signed in through that flow
as an employee holding view/convert/export on every module, which is what the
router tests need to reach the routers at all.

The HAP PDF fixtures are in the repository-root conftest.py and never were
identity's.
"""

from __future__ import annotations

import time
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from backend.maec_auth import session, verify

ISSUER = "http://core.test"
CLIENT_ID = "engineering-test-client"
CLIENT_SECRET = "test-client-secret-never-real"
REDIRECT_URI = "http://et.test/auth/callback"
KID = "test-signing-key"

ROLE_ID = "role-employee"
MODULES = ("hapext", "airsizer", "hapaudit", "rebadge")
ACTIONS = ("view", "convert", "export")


@pytest.fixture(scope="session")
def signing_key():
    """The key this run's miniature Core signs with."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="session")
def forger_key():
    """A key Core never publishes. Anything it signs must be refused."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def core_claims(**overrides) -> dict:
    """A claim set shaped exactly like Core's tokens, for one engineer."""
    now = int(time.time())
    claims = {
        "iss": ISSUER, "sub": "user-engineer", "aud": "engineering",
        "org": "org-mirage", "email": "engineer@mirageaec.com",
        "name": "Test Engineer", "pv": 1, "nonce": "unset", "jti": "jti-1",
        "iat": now, "exp": now + 15 * 60,
        "entitled": True, "entitled_until": None,
        "grants": [{"role": "employee", "role_id": ROLE_ID,
                    "scope_type": "application", "scope_id": "engineering",
                    "expires_at": None}],
        "role_permissions": {ROLE_ID: {f"engineering:{m}:{a}": "allow"
                                       for m in MODULES for a in ACTIONS}},
        "tool_rules": [],
    }
    claims.update(overrides)
    return claims


@pytest.fixture
def mint(signing_key):
    """Sign claims the way Core does: RS256, kid in the header."""
    def _mint(claims: dict | None = None, *, key=None, kid: str = KID,
              algorithm: str = "RS256") -> str:
        return jwt.encode(claims or core_claims(), key or signing_key,
                          algorithm=algorithm, headers={"kid": kid})
    return _mint


@pytest.fixture
def jwks_fetches():
    """Every URL verify.py asked for keys, in order."""
    return []


@pytest.fixture(autouse=True)
def miniature_core(monkeypatch, signing_key, jwks_fetches):
    """Point the client at a Core that lives in this process.

    Autouse, because every test in this directory runs against an app whose
    configuration would otherwise be read from the developer's own
    environment — and whose sessions and cached keys would leak from one test
    into the next.
    """
    for name, value in {
        "OIDC_ISSUER": ISSUER,
        "OIDC_CLIENT_ID": CLIENT_ID,
        "OIDC_CLIENT_SECRET": CLIENT_SECRET,
        "OIDC_REDIRECT_URI": REDIRECT_URI,
        "ET_SESSION_SECRET": "test-session-secret",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("RENDER", raising=False)

    public = jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key(), as_dict=True)
    public.update({"kid": KID, "alg": "RS256", "use": "sig"})

    def fake_get(url, *args, **kwargs):
        jwks_fetches.append(url)
        return httpx.Response(
            200, json={"keys": [public]},
            headers={"cache-control": "public, max-age=300"},
            request=httpx.Request("GET", url))

    monkeypatch.setattr(verify.httpx, "get", fake_get)
    verify.reset_cache()
    session.clear_all()
    yield
    verify.reset_cache()
    session.clear_all()


@pytest.fixture
def app_client():
    """A browser that has not signed in."""
    from backend.main import app
    return TestClient(app)


@pytest.fixture
def sign_in(monkeypatch, mint):
    """Sign a client in through the real flow; returns (callback response, exchanges).

    `claims` overrides parts of the engineer's claim set. `token` replaces the
    token Core would return outright — how the forged and wrong-audience cases
    reach the callback. The nonce is taken from the /auth/login redirect, so a
    minted token carries the one this sign-in issued unless the test says
    otherwise.
    """
    def _sign_in(client: TestClient, *, claims: dict | None = None,
                 token: str | None = None, state: str | None = None):
        launched = client.get("/auth/login", follow_redirects=False)
        assert launched.status_code == 302, launched.text
        query = parse_qs(urlparse(launched.headers["location"]).query)
        issued_state, issued_nonce = query["state"][0], query["nonce"][0]
        returned = token or mint(core_claims(**{"nonce": issued_nonce, **(claims or {})}))

        exchanges: list[tuple[str, dict]] = []

        def fake_post(url, data=None, **kwargs):
            exchanges.append((url, dict(data or {})))
            return httpx.Response(
                200, json={"access_token": returned, "token_type": "Bearer",
                           "expires_in": 900},
                headers={"cache-control": "no-store"},
                request=httpx.Request("POST", url))

        monkeypatch.setattr(httpx, "post", fake_post)
        callback = client.get("/auth/callback",
                              params={"code": "one-time-code",
                                      "state": issued_state if state is None else state},
                              follow_redirects=False)
        return callback, exchanges
    return _sign_in


@pytest.fixture
def engineer_client(sign_in):
    """Signed in as an engineer with view/convert/export on every module."""
    from backend.main import app
    client = TestClient(app)
    callback, _ = sign_in(client)
    assert callback.status_code == 302, callback.text
    return client
