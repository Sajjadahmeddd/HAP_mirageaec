"""What guards Engineering Tools — and, right now, what does not.

This file used to test the sign-in gate. Sign-in is Core's now, and moved to
the maec-one-core repository with it. What is left here is the half that was
never Core's: **Engineering Tools' own requirement that its routes refuse a
stranger.** That requirement has not changed. Only the mechanism has, and the
new mechanism does not exist yet.

So the file is in two parts:

  * live tests that pin the state this branch is actually in, including the
    fact that every product route currently answers anybody at all;
  * skipped tests naming what the OIDC client has to restore, kept as
    executable specification rather than prose, because a checklist in a
    commit message is a checklist nobody runs.

**This branch must not be merged.** Deployed as it stands, Engineering Tools
is a publicly reachable HAP converter. The live tests below say so out loud
so that the state cannot be mistaken for a passing suite.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app

# Every product route that must never answer a stranger. Unchanged from when
# Core enforced it — this list is the specification the token guard inherits.
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
]

DOCS = ["/docs", "/redoc", "/openapi.json"]

NEXT = "Restored by the OIDC client: verification against Core's JWKS."


@pytest.fixture
def client():
    return TestClient(app)


# ------------------------------------------------ the state this branch is in
@pytest.mark.parametrize("method,path", GUARDED)
def test_every_product_route_is_currently_unauthenticated(client, method, path):
    """The hole, pinned deliberately.

    A 401 would mean something still refuses strangers. Nothing does: the
    request reaches the route, and the route answers on its own terms — 200
    when it needs no body, 422 when it wants one it did not get. Either way
    it was *reached*, by a client that never identified itself.

    This test exists to fail the day authentication returns, so that whoever
    restores it has to come here and turn this file back into the guarantee
    it used to be. Delete it then; do not relax it.
    """
    assert client.request(method, path).status_code != 401


@pytest.mark.parametrize("path", DOCS)
def test_the_api_docs_are_currently_open_to_anybody(client, path):
    """They enumerate every route and its schema. Same tripwire as above."""
    assert client.get(path).status_code == 200


def test_health_does_not_claim_an_authentication_it_does_not_have(client):
    """It used to report `auth: on`, and that was true. Saying so now would
    be a health check lying about the one thing it is asked to be honest
    about."""
    assert client.get("/api/health").json()["auth"] == "none"


def test_the_spa_shell_is_still_served(client):
    """Unchanged and still true: the bundle is served at every non-API path.
    Under Core it had to be, so a login screen could load. Now it simply is
    the application."""
    assert client.get("/").status_code == 200


def test_the_security_headers_survive_the_split(client):
    """The CSP and its neighbours were never part of the gate — they are the
    one protection on this branch that still works exactly as before."""
    assert "Content-Security-Policy" in client.get("/").headers


# ------------------------------------------- what the OIDC client must restore
@pytest.mark.skip(reason=NEXT)
@pytest.mark.parametrize("method,path", GUARDED)
def test_every_product_route_refuses_a_stranger(method, path):
    """The requirement this file exists for. It did not stop being true when
    Core moved out; it stopped being enforced."""


@pytest.mark.skip(reason=NEXT)
def test_a_forged_token_is_rejected():
    """Was: a forged session cookie. The shape carries over exactly — a
    signature this service did not issue and cannot verify against Core's
    published keys is refused, not merely ignored."""


@pytest.mark.skip(reason=NEXT)
def test_a_token_for_another_audience_is_rejected():
    """New, and only meaningful once the services are separate: a token Core
    minted for a different client must not open Engineering Tools. `aud` is
    what makes eight applications on one issuer safe."""


@pytest.mark.skip(reason=NEXT)
def test_an_expired_token_is_rejected():
    """Also new. Under a shared database the guard re-read the account on
    every request, so a suspension bit immediately. A token cannot do that;
    what replaces it is a short lifetime. See the next test."""


@pytest.mark.skip(reason=NEXT)
def test_a_suspended_account_loses_access_within_the_token_lifetime():
    """The property most at risk in the split, and the one worth arguing
    about before it is built.

    Today suspension takes effect on the very next request, because the
    guard reads the user row every time. After the split Engineering Tools
    has no user row to read, and the honest guarantee becomes "within the
    token's lifetime". How long that is *is* the security decision — see
    OPEN-DECISIONS #11. This test should assert the number that decision
    lands on, not a vague "eventually".
    """


@pytest.mark.skip(reason=NEXT)
def test_a_person_without_a_seat_cannot_reach_the_product_api():
    """Entitlement, enforced from a claim rather than from a licence row.
    Core decides it; Engineering Tools must refuse on it. Unentitled means
    unusable, not merely hidden."""


@pytest.mark.skip(reason=NEXT)
def test_a_session_does_not_leak_between_clients():
    """Carried over unchanged. One browser's credentials must never answer
    for another's, whatever the credential is made of."""


@pytest.mark.skip(reason=NEXT)
@pytest.mark.parametrize("path", DOCS)
def test_the_api_docs_are_not_readable_by_a_stranger(path):
    """They were behind the gate. They belong behind the new one."""
