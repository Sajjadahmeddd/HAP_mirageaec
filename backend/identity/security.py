"""Passwords, sessions and the CSRF token.

Hashing is argon2id (argon2-cffi's default). Nothing reversible is ever
stored, and nothing here logs or returns a hash.

The session is Starlette's signed cookie. What goes in it is small and
deliberate: the user id, the permissions version the session was issued
against, a random session id that changes on every login, and the CSRF
token. Nothing a request could be tricked into trusting is derived from the
cookie alone — the user is re-read from the database on every guarded call.
"""

from __future__ import annotations

import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Request

from . import config

# Session keys. Short, because every request carries them.
S_USER = "uid"        # user id, as a string
S_VERSION = "pv"      # permissions_version at issue
S_ID = "sid"          # changes on every login — the fixation defence
S_CSRF = "csrf"

_hasher = PasswordHasher()   # argon2id, library defaults

# One real hash of a random password, verified against on every failed
# lookup so a request for an unknown address costs the same time as a wrong
# password for a known one.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(24))


# -------------------------------------------------------------- passwords
def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Constant-work verification. A missing hash still burns one argon2."""
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password)
    except (VerifyMismatchError, InvalidHashError):
        return False
    except Exception:
        return False              # fail closed, whatever went wrong


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except Exception:
        return False


MIN_PASSWORD_LENGTH = 12

# Not a breach list — the handful of values that appear in every one.
OBVIOUS = frozenset({
    "password", "password1", "password123", "passw0rd", "p@ssword",
    "123456", "12345678", "123456789", "1234567890", "123456789012",
    "qwerty", "qwertyuiop", "letmein", "welcome", "welcome1", "admin",
    "administrator", "changeme", "iloveyou", "abc123", "monkey", "dragon",
    "mirage", "mirageaec", "maec", "hapext", "engineering",
})


class WeakPasswordError(ValueError):
    pass


def check_password_policy(password: str, *, email: str = "") -> None:
    """Raise if this password would not be accepted. Server-side, always."""
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    lowered = password.strip().lower()
    if lowered in OBVIOUS or lowered.rstrip("0123456789!@#$%^&*") in OBVIOUS:
        raise WeakPasswordError("That password is too common to be safe.")
    if email:
        local = email.split("@", 1)[0].lower()
        if local and len(local) >= 4 and local in lowered:
            raise WeakPasswordError("Password must not contain your email address.")


# --------------------------------------------------------------- sessions
def constant_time_equal(a: str | None, b: str | None) -> bool:
    return hmac.compare_digest((a or "").encode(), (b or "").encode())


def start_session(request: Request, *, user_id: str, permissions_version: int) -> None:
    """A fresh session for a freshly verified user.

    Everything from before is discarded, and the session id and CSRF token
    are new — so a cookie planted before login is worthless after it.
    """
    request.session.clear()
    request.session[S_USER] = user_id
    request.session[S_VERSION] = int(permissions_version)
    request.session[S_ID] = secrets.token_urlsafe(24)
    request.session[S_CSRF] = secrets.token_urlsafe(32)


def end_session(request: Request) -> None:
    try:
        request.session.clear()
    except AssertionError:
        pass                      # no SessionMiddleware — nothing to clear


def session_user_id(request: Request) -> str | None:
    try:
        value = request.session.get(S_USER)
    except AssertionError:
        return None
    return str(value) if value else None


def session_id(request: Request) -> str | None:
    return request.session.get(S_ID)


def csrf_token(request: Request) -> str | None:
    return request.session.get(S_CSRF)


def csrf_ok(request: Request) -> bool:
    """The header must match the token the session holds. Constant time."""
    expected = csrf_token(request)
    supplied = request.headers.get(config.CSRF_HEADER)
    if not expected or not supplied:
        return False
    return constant_time_equal(expected, supplied)
