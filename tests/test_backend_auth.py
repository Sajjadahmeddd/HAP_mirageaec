"""The sign-in gate.

A Render service has a public URL, so these tests are the ones that keep the
app from being open to anyone holding the link. Signing in is mandatory:
there must be no configuration under which the API answers a stranger.
"""

import logging
import time

import pytest
from fastapi.testclient import TestClient

from backend import auth
from backend.main import app

PASSWORD = "test-team-password"
EMAIL = auth.DEFAULT_EMAIL

# Captured at import, before the autouse fixture below zeroes it, so the
# value that ships can still be asserted on.
SHIPPED_DELAY = auth.FAILED_LOGIN_DELAY_SECONDS

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


@pytest.fixture(autouse=True)
def no_failed_login_delay(monkeypatch):
    """Every wrong password here would otherwise cost a real second.

    The delay is deliberately removed for the rest of the file and tested on
    its own in `test_a_failed_sign_in_is_delayed`, so this fixture cannot hide
    its removal from production code.
    """
    monkeypatch.setattr(auth, "FAILED_LOGIN_DELAY_SECONDS", 0)


@pytest.fixture
def locked(monkeypatch):
    """A client with the gate switched on, nobody signed in."""
    monkeypatch.setenv("MAEC_PASSWORD", PASSWORD)
    monkeypatch.delenv("MAEC_EMAIL", raising=False)
    return TestClient(app)


@pytest.fixture
def unconfigured(monkeypatch):
    """No env vars at all — nothing may be accepted, by anyone.

    `TestClient(app)` without a `with` block does not run the lifespan, so
    this is the app as it would be if the startup refusal were somehow
    bypassed. It must still admit nobody.
    """
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


@pytest.mark.parametrize("attempt", ["", "hapext", "anything", PASSWORD])
def test_nothing_is_accepted_when_no_password_is_configured(unconfigured, attempt):
    """There is no built-in password, so there is nothing to guess.

    "hapext" is named explicitly: it was the committed fallback, it was live
    on a public URL, and it must never be a working credential again.
    """
    assert sign_in(unconfigured, password=attempt).status_code == 401


def test_the_configured_password_is_the_only_one_that_works(locked):
    assert sign_in(locked, password=PASSWORD).status_code == 200
    assert sign_in(locked, password="hapext").status_code == 401


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
def test_verify_rejects_everything_when_no_password_is_configured(monkeypatch):
    """An email alone grants nothing, and neither does an empty password."""
    monkeypatch.delenv("MAEC_PASSWORD", raising=False)
    assert auth.verify(auth.DEFAULT_EMAIL, "anything") is False
    assert auth.verify(auth.DEFAULT_EMAIL, "") is False
    assert auth.password() == ""


@pytest.mark.parametrize("too_short", ["a", "short", "1234567"])
def test_verify_rejects_everything_when_the_password_is_too_short(monkeypatch, too_short):
    """Fail closed: a password below the minimum admits nobody, not even
    whoever set it. Startup refuses first; this is the second lock."""
    monkeypatch.setenv("MAEC_PASSWORD", too_short)
    assert auth.verify(auth.DEFAULT_EMAIL, too_short) is False
    assert auth.password_problem() != ""


def test_a_password_of_exactly_the_minimum_length_is_accepted(monkeypatch):
    """The boundary belongs to the user, not to the guard."""
    monkeypatch.setenv("MAEC_PASSWORD", "8charpwd")
    assert len("8charpwd") == auth.MIN_PASSWORD_LENGTH
    assert auth.password_problem() == ""
    assert auth.verify(auth.DEFAULT_EMAIL, "8charpwd") is True


def test_the_refusal_message_states_the_requirement(monkeypatch):
    """Whoever reads this is mid-deploy and needs to know what to set."""
    monkeypatch.delenv("MAEC_PASSWORD", raising=False)
    unset = auth.password_problem()
    monkeypatch.setenv("MAEC_PASSWORD", "short")
    short = auth.password_problem()
    for message in (unset, short):
        assert "MAEC_PASSWORD" in message
        assert str(auth.MIN_PASSWORD_LENGTH) in message
    assert "no built-in password" in unset


@pytest.mark.parametrize("value", ["", "short"])
def test_the_app_refuses_to_start_without_a_usable_password(monkeypatch, value):
    """The startup guard itself, which only a lifespan run exercises.

    `with TestClient(app)` is what runs the lifespan — a bare TestClient does
    not — so without the `with` this guard could be deleted and every other
    test here would still pass.
    """
    if value:
        monkeypatch.setenv("MAEC_PASSWORD", value)
    else:
        monkeypatch.delenv("MAEC_PASSWORD", raising=False)

    with pytest.raises(RuntimeError, match="refuses to start"):
        with TestClient(app):
            pass


def test_the_app_starts_with_a_usable_password(monkeypatch):
    """The other half: the guard must not block a correct deployment."""
    monkeypatch.setenv("MAEC_PASSWORD", PASSWORD)
    with TestClient(app) as started:
        assert started.get("/api/health").json()["auth"] == "on"


# ---------------------------------------------------------- who we greet
def test_the_launcher_is_told_who_signed_in(locked):
    """The launcher greets by name, so /me has to carry one."""
    assert locked.get("/api/auth/me").json()["name"] == ""      # nobody yet
    assert sign_in(locked).json()["name"] == auth.DEFAULT_NAME
    body = locked.get("/api/auth/me").json()
    assert body["name"] == auth.DEFAULT_NAME
    assert body["email"] == EMAIL


def test_the_display_name_can_be_overridden(monkeypatch):
    monkeypatch.setenv("MAEC_PASSWORD", PASSWORD)
    monkeypatch.setenv("MAEC_DISPLAY_NAME", "Mirage AEC India")
    client = TestClient(app)
    assert sign_in(client).json()["name"] == "Mirage AEC India"


def test_the_display_name_falls_back_to_the_built_in_one(monkeypatch):
    monkeypatch.delenv("MAEC_DISPLAY_NAME", raising=False)
    assert auth.display_name() == auth.DEFAULT_NAME


# ------------------------------------------------------------- the docs
# FastAPI's docs map every endpoint and its request shape. They live outside
# /api/, so they need naming explicitly — and a test, so a later refactor of
# requires_auth cannot quietly reopen them.
DOCS = ["/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"]


@pytest.mark.parametrize("path", DOCS)
def test_the_api_docs_are_not_readable_by_a_stranger(locked, path):
    assert locked.get(path).status_code == 401


@pytest.mark.parametrize("path", DOCS)
def test_the_api_docs_open_once_signed_in(locked, path):
    """Gated, not removed: staff still get them on the running service."""
    sign_in(locked)
    assert locked.get(path).status_code == 200


def test_the_docs_stay_shut_with_nothing_configured(unconfigured):
    assert unconfigured.get("/openapi.json").status_code == 401


def test_requires_auth_covers_the_docs():
    for path in DOCS:
        assert auth.requires_auth(path) is True


def test_requires_auth_covers_the_api_but_not_the_shell():
    assert auth.requires_auth("/api/airsizer/config") is True
    assert auth.requires_auth("/api/hapext/convert") is True
    assert auth.requires_auth("/api/auth/login") is False
    assert auth.requires_auth("/api/health") is False
    assert auth.requires_auth("/") is False
    assert auth.requires_auth("/assets/index.js") is False


# ------------------------------------------------- cost of a wrong password
def test_the_delay_is_long_enough_to_matter():
    """A guessing rate of one per second, set in the source, not in a test."""
    assert SHIPPED_DELAY >= 1.0


def test_a_failed_sign_in_is_delayed(locked, monkeypatch):
    monkeypatch.setattr(auth, "FAILED_LOGIN_DELAY_SECONDS", 0.4)
    started = time.perf_counter()
    assert sign_in(locked, password="wrong").status_code == 401
    assert time.perf_counter() - started >= 0.4


def test_a_correct_sign_in_is_not_delayed(locked, monkeypatch):
    """The cost falls on guessing, never on the person who got it right."""
    monkeypatch.setattr(auth, "FAILED_LOGIN_DELAY_SECONDS", 5)
    started = time.perf_counter()
    assert sign_in(locked).status_code == 200
    assert time.perf_counter() - started < 1


# ------------------------------------------------------ the attempt log
def test_a_failed_sign_in_is_logged_as_a_warning(locked, caplog):
    with caplog.at_level(logging.INFO, logger="maec.auth"):
        sign_in(locked, email="stranger@example.com", password="wrong")

    record = next(r for r in caplog.records if r.name == "maec.auth")
    assert record.levelno == logging.WARNING
    assert "FAILED" in record.message
    assert "stranger@example.com" in record.message
    assert "client=" in record.message


def test_a_successful_sign_in_is_logged_too(locked, caplog):
    """Without the successes, the failures cannot be read in context."""
    with caplog.at_level(logging.INFO, logger="maec.auth"):
        sign_in(locked)

    record = next(r for r in caplog.records if r.name == "maec.auth")
    assert record.levelno == logging.INFO
    assert "SUCCEEDED" in record.message


def test_the_log_never_carries_the_password(locked, caplog):
    """The one thing that must never reach a log file."""
    secret = "a-very-distinctive-password"
    with caplog.at_level(logging.INFO, logger="maec.auth"):
        sign_in(locked, password=secret)
        sign_in(locked, password=PASSWORD)

    for record in caplog.records:
        assert secret not in record.getMessage()
        assert PASSWORD not in record.getMessage()


def test_the_log_records_the_forwarded_address_as_claimed(locked, caplog):
    """On Render the proxy sets this header, but a caller can invent one --
    so it is recorded raw and labelled, never treated as the true source."""
    with caplog.at_level(logging.INFO, logger="maec.auth"):
        locked.post(
            "/api/auth/login",
            json={"email": EMAIL, "password": "wrong"},
            headers={"X-Forwarded-For": "203.0.113.9, 70.41.3.18"},
        )

    message = next(r for r in caplog.records if r.name == "maec.auth").getMessage()
    assert "claimed-xff=203.0.113.9, 70.41.3.18" in message
    assert "client=" in message


def test_a_hostile_address_cannot_forge_a_second_log_line(locked, caplog):
    """The address comes from the request body: a newline in it would let a
    caller write their own log entry."""
    with caplog.at_level(logging.INFO, logger="maec.auth"):
        sign_in(locked, email="x@y.com\nsign-in SUCCEEDED at 2026-01-01", password="w")

    message = next(r for r in caplog.records if r.name == "maec.auth").getMessage()
    # The forged text survives as *content* of the email field, which is
    # honest; what it must not do is become a line of its own.
    assert "\n" not in message
    assert message.startswith("sign-in FAILED")


def test_a_very_long_address_is_truncated_in_the_log(locked, caplog):
    with caplog.at_level(logging.INFO, logger="maec.auth"):
        sign_in(locked, email="a" * 5000 + "@example.com", password="w")

    message = next(r for r in caplog.records if r.name == "maec.auth").getMessage()
    assert len(message) < 600


def test_logging_is_configured_so_successes_are_not_dropped():
    """uvicorn leaves the root logger alone, so INFO would go unheard."""
    auth.configure_logging()
    assert auth.logger.level == logging.INFO

    before = list(auth.logger.handlers)
    auth.configure_logging()          # startup can run more than once
    assert auth.logger.handlers == before
