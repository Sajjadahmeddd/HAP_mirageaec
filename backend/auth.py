"""Access control for the web app.

A Render service has a public URL, so without this anyone holding the link
could upload reports and pull schedules. This closes that.

**Mode: one shared account, always required.** There is no configuration
that leaves the app open, and there is no built-in password to fall back on:
`MAEC_PASSWORD` must be set to at least `MIN_PASSWORD_LENGTH` characters or
the app refuses to start, and `verify()` refuses every attempt meanwhile. No
database, no user records, nothing for us to store beyond a single secret
that Render already encrypts at rest.

The session is a *signed cookie* — there is no server-side session store, so
the app stays stateless and survives a Render restart or a second instance
without any shared state.

Upgrading to per-user logins later is deliberately a small change: everything
below the `verify()` function stays as it is, and only `verify()` grows a
username lookup against bcrypt hashes. The guard, the cookie, the routes and
the whole frontend are unaffected.
"""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/auth", tags=["auth"])

SESSION_KEY = "maec_auth"
SESSION_MAX_AGE = 12 * 60 * 60          # one working day

logger = logging.getLogger("maec.auth")


def configure_logging() -> None:
    """Make sure the sign-in log is actually emitted under uvicorn.

    uvicorn configures its own loggers and leaves the root logger alone, so
    without this a successful sign-in (INFO) is dropped and only failures
    (WARNING) escape, via logging's last-resort handler. The successes are
    what give the failures context, so they have to survive.

    A handler is added only when nothing else is configured to take it;
    where the host already set logging up, that configuration wins and this
    does not double every line.
    """
    logger.setLevel(logging.INFO)
    if not logger.handlers and not logging.getLogger().handlers:
        handler = logging.StreamHandler()
        # The message carries its own UTC timestamp, so the format stays bare
        # rather than printing a second, differently-shaped one beside it.
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        logger.addHandler(handler)

# Paid on a failed sign-in only, so a correct password is never slowed down.
# One shared account cannot be locked out -- a lockout would hand any stranger
# the power to shut the team out of their own tool -- so the cost of guessing
# is charged in time instead. At a second per try, a password of the minimum
# length is not reachable by guessing, and a person who mistypes theirs waits
# one second.
FAILED_LOGIN_DELAY_SECONDS = 1.0

# A log line must survive being read months later by someone who was not here
# when it was written, and must never become an attack of its own: an address
# arrives from the request body, so it is trimmed and stripped of the newlines
# that would let it forge a second log line.
_MAX_LOGGED_EMAIL = 120

# Paths reachable without signing in: the login exchange itself and the
# health probe Render polls.
PUBLIC_PREFIXES = ("/api/auth/", "/api/health")

# FastAPI serves its own docs outside /api/, so the rule below would let them
# through. They map every endpoint and its request shape — reconnaissance a
# stranger should not get for free — so they are named here explicitly.
# Signed-in staff still get them, which is when they are actually wanted.
DOCS_PREFIXES = ("/docs", "/redoc", "/openapi.json")


# Signing in is mandatory: there is no configuration that leaves the app open.
# The address has a default because it is not a secret; the password has none
# on purpose. A committed password is readable by everyone with repository
# access, and a service on a public URL ran on exactly that for months.
DEFAULT_EMAIL = "mirageaec@mirage.com"

# Short enough not to be a nuisance for a shared team account, long enough
# that the password cannot be a word someone guesses on the first try.
MIN_PASSWORD_LENGTH = 8

# Who the launcher greets. One shared account for now, so this is simply
# configuration; when per-user logins land it becomes the signed-in user's
# own name and nothing on the frontend has to change.
DEFAULT_NAME = "Mirage AEC"


def email() -> str:
    return (os.environ.get("MAEC_EMAIL", "").strip() or DEFAULT_EMAIL).lower()


def password() -> str:
    """The configured password, or "" when there is none. No fallback."""
    return os.environ.get("MAEC_PASSWORD", "").strip()


def display_name() -> str:
    return os.environ.get("MAEC_DISPLAY_NAME", "").strip() or DEFAULT_NAME


def is_enabled() -> bool:
    """Always. Kept as a function so the frontend contract does not change."""
    return True


def password_problem() -> str:
    """Why MAEC_PASSWORD cannot be used, or "" when it is usable.

    Startup calls this and refuses to run if it returns anything, so a
    deployment cannot come up with no password or a trivial one. The message
    states the requirement rather than only the failure — whoever sees it is
    usually mid-deploy and needs to know what to set, not just that something
    is wrong.
    """
    value = password()
    if not value:
        return (
            "MAEC_PASSWORD is not set, and there is no built-in password to "
            f"fall back on. Set it to at least {MIN_PASSWORD_LENGTH} characters."
        )
    if len(value) < MIN_PASSWORD_LENGTH:
        return (
            f"MAEC_PASSWORD is {len(value)} characters. It must be at least "
            f"{MIN_PASSWORD_LENGTH}."
        )
    return ""


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

    With no usable password configured nothing can match: an empty or too
    short `MAEC_PASSWORD` refuses everyone rather than admitting anyone who
    posts an empty password. Startup already refuses in that state; this is
    the second lock, for a process that somehow got past the first.
    """
    if password_problem():
        return False

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
    """The API and the docs are guarded; the SPA shell itself must load to
    show a login screen at all.

    Anything new under /api/ is covered without touching this — which is the
    point, with more modules to come.
    """
    if path.startswith(DOCS_PREFIXES):
        return True
    if not path.startswith("/api/"):
        return False
    return not path.startswith(PUBLIC_PREFIXES)


def _for_log(value: str, limit: int = _MAX_LOGGED_EMAIL) -> str:
    """One line, bounded length. Never called with a password."""
    text = " ".join(str(value).split())
    return text[:limit] if text else "(none)"


def log_attempt(request: Request, supplied_email: str, *, succeeded: bool) -> None:
    """Record a sign-in attempt: when, what happened, and where from.

    The password is never logged, in any form. The address is, because
    without it the line cannot answer the only question worth asking of it
    later -- whether this was a colleague mistyping or somebody else.

    Both addresses are reported, and labelled for exactly what they are.

    `claimed-xff` is the `X-Forwarded-For` header verbatim. On Render the
    platform proxy sets it, but nothing stops a caller inventing one, so it
    is never treated as the truth — hence `claimed`.

    `client` is the address the server attributes to the connection. That is
    normally the socket peer, but uvicorn rewrites it from `X-Forwarded-For`
    when the peer is a trusted proxy (`--forwarded-allow-ips`, 127.0.0.1 by
    default), so on a request from localhost the two can agree because the
    caller said so. Behind Render's proxy or the nginx container, the peer is
    not in that list and this stays the real connecting address.

    Neither value is proof on its own; together they are what an incident
    review has to work with.
    """
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    client = request.client.host if request.client else "unknown"
    forwarded = _for_log(request.headers.get("x-forwarded-for", ""), limit=200)
    line = (
        "sign-in %s at %s: email=%s claimed-xff=%s client=%s",
        "SUCCEEDED" if succeeded else "FAILED",
        timestamp,
        _for_log(supplied_email),
        forwarded,
        client,
    )
    if succeeded:
        logger.info(*line)
    else:
        logger.warning(*line)


# ------------------------------------------------------------------ routes
@router.get("/me")
async def me(request: Request):
    """Drives the frontend: show the app, or show the login screen."""
    signed_in = is_signed_in(request)
    return {
        "enabled": is_enabled(),
        "authenticated": signed_in,
        "email": request.session.get("email", "") if signed_in else "",
        "name": display_name() if signed_in else "",
        "mode": "shared-account",
    }


@router.post("/login")
async def login(request: Request, payload: dict):
    supplied_email = str(payload.get("email", ""))
    if not verify(supplied_email, str(payload.get("password", ""))):
        log_attempt(request, supplied_email, succeeded=False)
        # A wrong answer costs a second. Logged before the wait, so the record
        # exists even if the caller hangs up rather than waiting for the 401.
        await asyncio.sleep(FAILED_LOGIN_DELAY_SECONDS)
        # one message for both halves: never reveal which was wrong
        raise HTTPException(
            status_code=401, detail="Incorrect email address or password."
        )

    log_attempt(request, supplied_email, succeeded=True)
    request.session[SESSION_KEY] = True
    request.session["email"] = supplied_email.strip().lower()
    return {
        "authenticated": True,
        "enabled": True,
        "email": email(),
        "name": display_name(),
    }


@router.post("/logout")
async def logout(request: Request):
    try:
        request.session.clear()
    except AssertionError:
        pass
    return {"authenticated": False}
