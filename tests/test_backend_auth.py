"""The sign-in gate.

A Render service has a public URL, so these tests are the ones that keep the
app from being open to anyone holding the link. Signing in is mandatory:
there must be no configuration under which the API answers a stranger.
"""

import pytest
from fastapi.testclient import TestClient

from backend import auth
from backend.main import app

PASSWORD = "test-team-password"
EMAIL = auth.DEFAULT_EMAIL

# every route that must never answer to a stranger
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
]


@pytest.fixture
def locked(monkeypatch):
    """A client with the gate switched on, nobody signed in."""
    monkeypatch.setenv("MAEC_PASSWORD", PASSWORD)
    monkeypatch.delenv("MAEC_EMAIL", raising=False)
    return TestClient(app)


@pytest.fixture
def unconfigured(monkeypatch):
    """No env vars at all — the built-in credentials must still apply."""
    monkeypatch.delenv("MAEC_PASSWORD", raising=False)
    monkeypatch.delenv("MAEC_EMAIL", raising=False)
    return TestClient(app)


def sign_in(client, email=EMAIL, password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


# ------------------------------------------------- there is no "open" mode
def test_the_gate_cannot_be_switched_off(unconfigured):
    """With nothing configured the app still demands a sign-in."""
    assert unconfigured.get("/api/health").json()["auth"] == "on"
    body = unconfigured.get("/api/auth/me").json()
    assert body["enabled"] is True
    assert body["authenticated"] is False
    assert unconfigured.get("/api/airsizer/config").status_code == 401


def test_the_built_in_credentials_work_when_nothing_is_configured(unconfigured):
    assert sign_in(
        unconfigured, email=auth.DEFAULT_EMAIL, password=auth.DEFAULT_PASSWORD
    ).status_code == 200


def test_a_configured_password_overrides_the_built_in_one(locked):
    assert sign_in(locked, password=PASSWORD).status_code == 200
    assert sign_in(locked, password=auth.DEFAULT_PASSWORD).status_code == 401


# ------------------------------------------------------------------ gate on
def test_health_says_the_gate_is_on(locked):
    assert locked.get("/api/health").json()["auth"] == "on"


@pytest.mark.parametrize("method,path", GUARDED)
def test_every_api_route_refuses_a_stranger(locked, method, path):
    assert locked.request(method, path).status_code == 401


def test_public_paths_stay_reachable(locked):
    assert locked.get("/api/health").status_code == 200
    assert locked.get("/api/auth/me").status_code == 200


def test_the_spa_shell_is_always_served(locked):
    """It has to load, or there is no login screen to show."""
    assert locked.get("/").status_code == 200


def test_me_reports_signed_out_before_login(locked):
    body = locked.get("/api/auth/me").json()
    assert body["enabled"] is True
    assert body["authenticated"] is False
    assert body["email"] == ""


# ----------------------------------------------------------------- signing in
def test_correct_credentials_are_accepted(locked):
    response = sign_in(locked)
    assert response.status_code == 200
    assert response.json()["authenticated"] is True
    assert locked.get("/api/auth/me").json()["authenticated"] is True


def test_signing_in_opens_the_guarded_routes(locked):
    sign_in(locked)
    body = locked.get("/api/airsizer/config").json()
    assert len(body["diffusers"]) == 5


def test_a_wrong_password_is_refused(locked):
    assert sign_in(locked, password="wrong").status_code == 401


def test_a_wrong_email_is_refused(locked):
    assert sign_in(locked, email="stranger@example.com").status_code == 401


def test_both_failures_give_the_same_message(locked):
    """Never reveal which half was wrong."""
    wrong_email = sign_in(locked, email="stranger@example.com").json()["detail"]
    wrong_password = sign_in(locked, password="wrong").json()["detail"]
    assert wrong_email == wrong_password == "Incorrect email address or password."


def test_an_empty_password_is_refused(locked):
    assert sign_in(locked, password="").status_code == 401


def test_the_email_is_case_and_whitespace_tolerant(locked):
    """Nobody should be locked out by autocapitalise on a phone."""
    assert sign_in(locked, email=f"  {EMAIL.upper()}  ").status_code == 200


def test_the_email_can_be_overridden(monkeypatch):
    monkeypatch.setenv("MAEC_PASSWORD", PASSWORD)
    monkeypatch.setenv("MAEC_EMAIL", "someone.else@mirageaec.com")
    client = TestClient(app)
    assert sign_in(client, email=EMAIL).status_code == 401
    assert sign_in(client, email="someone.else@mirageaec.com").status_code == 200


# -------------------------------------------------------------- signing out
def test_signing_out_closes_the_routes_again(locked):
    sign_in(locked)
    assert locked.get("/api/airsizer/config").status_code == 200
    locked.post("/api/auth/logout")
    assert locked.get("/api/airsizer/config").status_code == 401
    assert locked.get("/api/auth/me").json()["authenticated"] is False


def test_a_session_does_not_leak_between_clients(monkeypatch):
    """One signed-in browser must not admit another."""
    monkeypatch.setenv("MAEC_PASSWORD", PASSWORD)
    signed_in, stranger = TestClient(app), TestClient(app)
    sign_in(signed_in)
    assert signed_in.get("/api/airsizer/config").status_code == 200
    assert stranger.get("/api/airsizer/config").status_code == 401


def test_a_forged_session_cookie_is_rejected(locked):
    """The cookie is signed; an invented one must not pass."""
    locked.cookies.set("maec_session", "eyJhdXRoIjogdHJ1ZX0=")   # {"auth": true}
    assert locked.get("/api/airsizer/config").status_code == 401


# --------------------------------------------------------------- the config
def test_verify_rejects_a_wrong_password(monkeypatch):
    """An email alone grants nothing."""
    monkeypatch.delenv("MAEC_PASSWORD", raising=False)
    assert auth.verify(auth.DEFAULT_EMAIL, "anything") is False
    assert auth.verify(auth.DEFAULT_EMAIL, auth.DEFAULT_PASSWORD) is True


def test_requires_auth_covers_the_api_but_not_the_shell():
    assert auth.requires_auth("/api/airsizer/config") is True
    assert auth.requires_auth("/api/hapext/convert") is True
    assert auth.requires_auth("/api/auth/login") is False
    assert auth.requires_auth("/api/health") is False
    assert auth.requires_auth("/") is False
    assert auth.requires_auth("/assets/index.js") is False
