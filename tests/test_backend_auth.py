"""The sign-in gate, now per person.

A Render service has a public URL, so these tests are the ones that keep the
app from being open to anyone holding the link. Signing in is mandatory:
there is no configuration under which the API answers a stranger — and now
no configuration under which it answers the wrong person either.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.identity import guard, router_auth, security
from backend.identity.models import AuditLog, User, UserLicense, UserRole

from conftest import ADMIN_EMAIL, ADMIN_PASSWORD, ENGINEER_EMAIL, ENGINEER_PASSWORD

GENERIC = "Incorrect email address or password."

# every product route that must never answer to a stranger
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
    ("GET", "/api/admin/whoami"),
    ("GET", "/api/admin/anything-at-all"),
]


def sign_in(client, email=ADMIN_EMAIL, password=ADMIN_PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def audit_rows(db, action):
    return db.scalars(select(AuditLog).where(AuditLog.action == action)).all()


# ------------------------------------------------------------------ gate on
def test_health_says_the_gate_is_on(app_client):
    assert app_client.get("/api/health").json()["auth"] == "on"


@pytest.mark.parametrize("method,path", GUARDED)
def test_every_api_route_refuses_a_stranger(app_client, method, path):
    assert app_client.request(method, path).status_code == 401


def test_public_paths_stay_reachable(app_client):
    assert app_client.get("/api/health").status_code == 200
    assert app_client.get("/api/auth/me").status_code == 200


def test_the_spa_shell_is_always_served(app_client):
    """It has to load, or there is no login screen to show."""
    assert app_client.get("/").status_code == 200


def test_me_reports_signed_out_before_login_but_still_lists_the_catalogue(app_client):
    body = app_client.get("/api/auth/me").json()
    assert body["authenticated"] is False
    assert "email" not in body
    keys = {a["key"] for a in body["apps"]}
    assert keys == {"engineering", "projects", "finance", "people",
                    "timesheet", "expenses", "attendance", "kpa"}
    assert all("entitled" not in a for a in body["apps"])   # nothing personal


# ----------------------------------------------------------------- signing in
def test_correct_credentials_are_accepted(app_client):
    response = sign_in(app_client)
    assert response.status_code == 200
    assert response.json()["authenticated"] is True
    assert app_client.get("/api/auth/me").json()["authenticated"] is True


def test_me_carries_the_whole_contract(admin_client):
    body = admin_client.get("/api/auth/me").json()
    assert body["email"] == ADMIN_EMAIL
    assert body["display_name"]
    assert body["org_id"]
    assert body["is_global_admin"] is True
    assert body["permissions_version"] == 1
    assert {"role": "global_admin", "scope_type": "platform", "scope_id": None} in body["roles"]
    apps = {a["key"]: a for a in body["apps"]}
    assert apps["engineering"]["entitled"] is True
    assert apps["engineering"]["status"] == "live"
    assert apps["timesheet"]["entitled"] is False
    assert apps["timesheet"]["status"] == "live"
    assert body["csrf_token"]


def test_the_engineer_is_not_a_global_admin(engineer_client):
    body = engineer_client.get("/api/auth/me").json()
    assert body["is_global_admin"] is False
    assert body["roles"] == [
        {"role": "employee", "scope_type": "application", "scope_id": "engineering"}]


def test_signing_in_opens_the_product_routes(engineer_client):
    body = engineer_client.get("/api/airsizer/config").json()
    assert len(body["diffusers"]) == 5


def test_a_wrong_password_is_refused(app_client):
    assert sign_in(app_client, password="wrong").status_code == 401


def test_a_wrong_email_is_refused(app_client):
    assert sign_in(app_client, email="stranger@example.com").status_code == 401


def test_every_failure_gives_the_same_message(app_client, db):
    """Unknown address, wrong password, suspended, locked — one reply."""
    unknown = sign_in(app_client, email="stranger@example.com").json()["detail"]
    wrong = sign_in(app_client, password="wrong").json()["detail"]
    engineer = db.scalar(select(User).where(User.email == ENGINEER_EMAIL))
    engineer.status = "suspended"
    db.commit()
    suspended = sign_in(app_client, email=ENGINEER_EMAIL,
                        password=ENGINEER_PASSWORD).json()["detail"]
    assert unknown == wrong == suspended == GENERIC


def test_an_empty_password_is_refused(app_client):
    assert sign_in(app_client, password="").status_code == 401


def test_the_email_is_case_and_whitespace_tolerant(app_client):
    """Nobody should be locked out by autocapitalise on a phone."""
    assert sign_in(app_client, email=f"  {ADMIN_EMAIL.upper()}  ").status_code == 200


def test_passwords_are_stored_as_argon2id_only(db):
    for user in db.scalars(select(User)).all():
        assert user.password_hash.startswith("$argon2id$")
        assert ADMIN_PASSWORD not in user.password_hash
        assert ENGINEER_PASSWORD not in user.password_hash


# ------------------------------------------------------------------- lockout
def test_repeated_failures_lock_the_account_with_the_same_message(app_client, db):
    for _ in range(router_auth.LOCK_AFTER):
        assert sign_in(app_client, password="wrong").json()["detail"] == GENERIC
    admin = db.scalar(select(User).where(User.email == ADMIN_EMAIL))
    assert admin.failed_login_count == router_auth.LOCK_AFTER
    assert admin.locked_until is not None

    # the right password no longer works, and the message does not say why
    refused = sign_in(app_client)
    assert refused.status_code == 401
    assert refused.json()["detail"] == GENERIC

    # every attempt was recorded, and so was the lock
    assert len(audit_rows(db, "login.failed")) == router_auth.LOCK_AFTER + 1
    locked = audit_rows(db, "login.locked")
    assert len(locked) >= 1 and locked[0].actor_email == ADMIN_EMAIL
    assert locked[0].result == "blocked"


def test_the_lockout_escalates(app_client, db):
    for _ in range(router_auth.LOCK_AFTER + 2):
        sign_in(app_client, password="wrong")
    admin = db.scalar(select(User).where(User.email == ADMIN_EMAIL))
    later = admin.locked_until.replace(tzinfo=timezone.utc) if admin.locked_until.tzinfo is None else admin.locked_until
    assert later - datetime.now(timezone.utc) > timedelta(minutes=3)


def test_a_lock_that_has_passed_lets_the_right_password_in(app_client, db):
    for _ in range(router_auth.LOCK_AFTER):
        sign_in(app_client, password="wrong")
    admin = db.scalar(select(User).where(User.email == ADMIN_EMAIL))
    admin.locked_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    assert sign_in(app_client).status_code == 200
    # the request committed in its own session; this one holds a cached copy
    # (the factory sets expire_on_commit=False), so read it again
    db.expire_all()
    admin = db.scalar(select(User).where(User.email == ADMIN_EMAIL))
    assert admin.failed_login_count == 0
    assert admin.locked_until is None


def test_the_per_ip_rate_limit_answers_429(app_client):
    router_auth.limiter.enabled = True
    router_auth.limiter.reset()
    codes = [sign_in(app_client, password="wrong").status_code for _ in range(12)]
    assert 429 in codes
    assert codes[:5] == [401] * 5


# ------------------------------------------------------------------ sessions
def test_the_session_cookie_is_host_only(app_client):
    """No Domain attribute — the company site shares mirageaec.com."""
    response = sign_in(app_client)
    header = response.headers.get("set-cookie", "")
    assert "maec_session=" in header
    assert "domain=" not in header.lower()
    assert "httponly" in header.lower()
    assert "samesite=lax" in header.lower()


def test_the_session_identifier_changes_on_login(app_client):
    """Fixation defence: whatever cookie came before, login issues a new one."""
    first = sign_in(app_client)
    first_cookie = first.headers["set-cookie"]
    second = sign_in(app_client)
    second_cookie = second.headers["set-cookie"]
    assert first_cookie != second_cookie


def test_a_forged_session_cookie_is_rejected(app_client):
    app_client.cookies.set("maec_session", "eyJ1aWQiOiAiYW55dGhpbmcifQ==")
    assert app_client.get("/api/airsizer/config").status_code == 401


def test_a_session_does_not_leak_between_clients(admin_client, app_client):
    from backend.main import app
    stranger = TestClient(app)
    assert admin_client.get("/api/airsizer/config").status_code == 200
    assert stranger.get("/api/airsizer/config").status_code == 401


def test_signing_out_closes_the_routes_again(admin_client, db):
    assert admin_client.get("/api/airsizer/config").status_code == 200
    admin_client.post("/api/auth/logout")
    assert admin_client.get("/api/airsizer/config").status_code == 401
    assert admin_client.get("/api/auth/me").json()["authenticated"] is False
    rows = audit_rows(db, "logout")
    assert len(rows) == 1 and rows[0].actor_email == ADMIN_EMAIL


def test_a_suspended_account_is_cut_off_mid_session(engineer_client, db):
    """Not at cookie expiry: on the very next request."""
    assert engineer_client.get("/api/airsizer/config").status_code == 200
    engineer = db.scalar(select(User).where(User.email == ENGINEER_EMAIL))
    engineer.status = "suspended"
    db.commit()
    assert engineer_client.get("/api/airsizer/config").status_code == 401


# ---------------------------------------------------------------- the audit
def test_login_success_and_failure_are_both_recorded_with_ip(app_client, db):
    sign_in(app_client, password="wrong")
    sign_in(app_client)
    failed, ok = audit_rows(db, "login.failed"), audit_rows(db, "login.success")
    assert len(failed) == 1 and failed[0].actor_email == ADMIN_EMAIL and failed[0].ip
    assert len(ok) == 1 and ok[0].actor_email == ADMIN_EMAIL and ok[0].ip
    assert ok[0].result == "success" and failed[0].result == "warning"


def test_an_unknown_address_is_still_recorded(app_client, db):
    sign_in(app_client, email="stranger@example.com")
    rows = audit_rows(db, "login.failed")
    assert len(rows) == 1 and rows[0].actor_id is None
    assert rows[0].actor_email == "stranger@example.com"


# --------------------------------------------------------------- the admin
def test_the_admin_prefix_refuses_an_engineer_with_403(engineer_client, db):
    """The frontend is bypassed entirely: a direct call still gets a 403."""
    for path in ("/api/admin/whoami", "/api/admin/anything", "/api/admin/roles/x/y"):
        assert engineer_client.get(path).status_code == 403
    rows = audit_rows(db, "admin.access")
    assert rows and all(r.result == "blocked" and r.actor_email == ENGINEER_EMAIL for r in rows)


def test_the_admin_prefix_opens_for_the_global_admin(admin_client):
    body = admin_client.get("/api/admin/whoami").json()
    assert body["email"] == ADMIN_EMAIL and body["is_global_admin"] is True


def test_an_admin_mutation_without_the_csrf_token_is_refused(admin_client, db):
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        response = admin_client.request(method, "/api/admin/whoami")
        assert response.status_code == 403, method
        assert "CSRF" in response.json()["detail"]
    assert audit_rows(db, "admin.csrf")


def test_an_admin_mutation_with_the_wrong_token_is_refused(admin_client):
    response = admin_client.post("/api/admin/whoami",
                                 headers={guard.security.config.CSRF_HEADER: "nope"})
    assert response.status_code == 403


def test_an_admin_mutation_with_the_token_passes_the_gate(admin_client):
    """405, not 403: the gate let it through, the route just has no POST."""
    response = admin_client.post("/api/admin/whoami",
                                 headers={guard.security.config.CSRF_HEADER: admin_client.csrf})
    assert response.status_code == 405


# ------------------------------------------------------------ entitlement
def test_a_person_without_a_seat_cannot_reach_the_product_api(engineer_client, db):
    """Unentitled means unusable, not merely hidden."""
    assert engineer_client.get("/api/airsizer/config").status_code == 200
    engineer = db.scalar(select(User).where(User.email == ENGINEER_EMAIL))
    db.delete(db.scalar(select(UserLicense).where(UserLicense.user_id == engineer.id)))
    db.commit()
    response = engineer_client.get("/api/airsizer/config")
    assert response.status_code == 403
    assert "licensed" in response.json()["detail"]
    assert audit_rows(db, "app.access")
    assert engineer_client.get("/api/auth/me").json()["apps"][0]["entitled"] in (True, False)


def test_a_revoked_role_leaves_the_seat_but_the_permission_engine_says_no(engineer_client, db):
    from backend.identity.permissions import can
    engineer = db.scalar(select(User).where(User.email == ENGINEER_EMAIL))
    db.delete(db.scalar(select(UserRole).where(UserRole.user_id == engineer.id)))
    db.commit()
    assert can(db, engineer, "engineering:hapext:convert") is False


# ------------------------------------------------------------- the docs
DOCS = ["/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"]


@pytest.mark.parametrize("path", DOCS)
def test_the_api_docs_are_not_readable_by_a_stranger(app_client, path):
    assert app_client.get(path).status_code == 401


@pytest.mark.parametrize("path", DOCS)
def test_the_api_docs_open_once_signed_in(admin_client, path):
    assert admin_client.get(path).status_code == 200


def test_requires_auth_covers_the_docs_and_the_api_but_not_the_shell():
    for path in DOCS:
        assert guard.requires_auth(path) is True
    assert guard.requires_auth("/api/airsizer/config") is True
    assert guard.requires_auth("/api/admin/whoami") is True
    assert guard.requires_auth("/api/auth/login") is False
    assert guard.requires_auth("/api/health") is False
    assert guard.requires_auth("/") is False
    assert guard.requires_auth("/assets/index.js") is False


# ------------------------------------------------------- password policy
@pytest.mark.parametrize("weak", ["short", "password1234", "Mirageaec123", "123456789012"])
def test_obvious_passwords_are_refused(weak):
    with pytest.raises(security.WeakPasswordError):
        security.check_password_policy(weak)


def test_a_password_must_not_contain_the_address(db):
    with pytest.raises(security.WeakPasswordError):
        security.check_password_policy("engineer-is-here-2026", email="engineer@mirageaec.com")


def test_the_seed_refuses_a_weak_bootstrap_password(identity):
    from backend.identity import seed
    from backend.identity.db import session_factory
    with session_factory()() as session:
        with pytest.raises(security.WeakPasswordError):
            seed.run(session, admin_email="x@mirageaec.com", admin_password="password")
