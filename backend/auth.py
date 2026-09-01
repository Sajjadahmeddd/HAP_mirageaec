"""Access control for the web app.

A Render service has a public URL, so without this anyone holding the link
could upload reports and pull schedules. This closes that.

**Mode: one shared account, always required.** There is no configuration
that leaves the app open — an unset `MAEC_PASSWORD` falls back to a built-in
default rather than disabling the gate. No database, no user records, nothing
for us to store beyond a single secret that Render already encrypts at rest.

The session is a *signed cookie* — there is no server-side session store, so
the app stays stateless and survives a Render restart or a second instance
without any shared state.

Upgrading to per-user logins later is deliberately a small change: everything
below the `verify()` function stays as it is, and only `verify()` grows a
username lookup against bcrypt hashes. The guard, the cookie, the routes and
the whole frontend are unaffected.
"""

from __future__ import annotations

import os
import secrets

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/auth", tags=["auth"])

SESSION_KEY = "maec_auth"
SESSION_MAX_AGE = 12 * 60 * 60          # one working day

# Paths reachable without signing in: the login exchange itself, the health
# probe Render polls, and the API docs.
PUBLIC_PREFIXES = ("/api/auth/", "/api/health")


# Signing in is mandatory: there is no configuration that leaves the app open.
# These defaults exist only so it works out of the box for testing — override
# both on Render, because anything committed here is visible to everyone with
# repository access.
DEFAULT_EMAIL = "mirageaec@mirage.com"
DEFAULT_PASSWORD = "hapext"


def email() -> str:
    return (os.environ.get("MAEC_EMAIL", "").strip() or DEFAULT_EMAIL).lower()


def password() -> str:
    return os.environ.get("MAEC_PASSWORD", "").strip() or DEFAULT_PASSWORD


def is_enabled() -> bool:
    """Always. Kept as a function so the frontend contract does not change."""
    return True


def using_default_password() -> bool:
    """True when nobody has overridden the built-in password."""
    return not os.environ.get("MAEC_PASSWORD", "").strip()


def secret_key() -> str:
    """Key that signs the session cookie.

    A generated fallback keeps local development frictionless, at the cost of
    signing everyone out on restart — fine locally, which is why deployment
    warns if it was not set explicitly.
    """
    configured = os.environ.get("MAEC_SECRET_KEY", "").strip()
    return configured or secrets.token_urlsafe(32)


def verify(supplied_email: str, supplied_password: str) -> bool:
    """Both must match. Constant-time, so a wrong guess leaks no timing signal.

    Both halves are always compared even when the first has already failed —
    returning early on a bad address would make wrong-email and wrong-password
    distinguishable by response time.
    """
    expected_password = password()
    email_ok = secrets.compare_digest(supplied_email.strip().lower(), email())
    password_ok = secrets.compare_digest(supplied_password.strip(), expected_password)
    return email_ok and password_ok


def is_signed_in(request: Request) -> bool:
    # Deliberately not defensive: if the session is missing here it means
    # SessionMiddleware is not wrapping this call, which is a wiring mistake
    # that must surface loudly rather than quietly denying every request.
    return bool(request.session.get(SESSION_KEY))


def requires_auth(path: str) -> bool:
    """Only the API is guarded; the SPA shell itself must load to show a
    login screen at all."""
    if not path.startswith("/api/"):
        return False
    return not path.startswith(PUBLIC_PREFIXES)


# ------------------------------------------------------------------ routes
@router.get("/me")
async def me(request: Request):
    """Drives the frontend: show the app, or show the login screen."""
    signed_in = is_signed_in(request)
    return {
        "enabled": is_enabled(),
        "authenticated": signed_in,
        "email": request.session.get("email", "") if signed_in else "",
        "mode": "shared-account",
    }


@router.post("/login")
async def login(request: Request, payload: dict):
    supplied_email = str(payload.get("email", ""))
    if not verify(supplied_email, str(payload.get("password", ""))):
        # one message for both halves: never reveal which was wrong
        raise HTTPException(
            status_code=401, detail="Incorrect email address or password."
        )

    request.session[SESSION_KEY] = True
    request.session["email"] = supplied_email.strip().lower()
    return {"authenticated": True, "enabled": True, "email": email()}


@router.post("/logout")
async def logout(request: Request):
    try:
        request.session.clear()
    except AssertionError:
        pass
    return {"authenticated": False}
