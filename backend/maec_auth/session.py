"""Engineering Tools' own session: an opaque id in a cookie, claims on the server.

The token stays on the server. A four-role token measures about 7.3 kB, which
is past the 4 kB a cookie may carry, so putting it in one does not merely leak
the claims to anything that can read the jar — it does not fit. The cookie
carries a signed random id and nothing else; the claims and the raw token live
in this process, keyed by that id.

The store is a dict in this process. That is right for one instance and wrong
for two: a second instance would not know the first's sessions, and a person
would be bounced back to Core on every other request. Moving it to Redis or a
table is the follow-up recorded in OPEN-DECISIONS #19 — the interface here is
already the one a shared store would implement, so the change is this file
and nothing else.

A session lives exactly as long as the token it was built from. Core fixed
that at fifteen minutes (#16), and this does not extend it: when the token's
`exp` passes, the session is stale and the browser is sent back for a fresh
one. That expiry is the replacement for the old guard's re-read of the user
row, and it is the reason a revoked seat now bites within fifteen minutes
rather than on the next call.
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any

from itsdangerous import BadSignature, URLSafeSerializer

from . import config


@dataclass
class Session:
    """One signed-in browser, as this service remembers it."""
    claims: dict[str, Any]
    token: str                 # the raw JWT: never leaves this process
    expires_at: float          # the token's own exp, in epoch seconds

    def alive(self, at: float | None = None) -> bool:
        return (at or time.time()) < self.expires_at

    @property
    def email(self) -> str:
        return str(self.claims.get("email", ""))

    @property
    def name(self) -> str:
        return str(self.claims.get("name", ""))


_lock = threading.Lock()
_sessions: dict[str, Session] = {}


def _serializer() -> URLSafeSerializer:
    """Signs the cookie so a forged or edited id is rejected before it is
    looked up. The id is already 256 bits of randomness; the signature is what
    keeps a guessed value from even reaching the store."""
    return URLSafeSerializer(config.session_secret(), salt="et-session")


def _purge(now: float) -> None:
    """Drop what has expired. Called on every write, which is often enough:
    sessions arrive one sign-in at a time and each is a few kilobytes."""
    for sid in [sid for sid, session in _sessions.items() if not session.alive(now)]:
        _sessions.pop(sid, None)


def create(claims: dict[str, Any], token: str) -> str:
    """Remember a verified sign-in. Returns the id to put in the cookie."""
    sid = secrets.token_urlsafe(32)
    now = time.time()
    with _lock:
        _purge(now)
        _sessions[sid] = Session(claims=claims, token=token,
                                 expires_at=float(claims["exp"]))
    return sid


def read(sid: str | None) -> Session | None:
    """The live session for this id, or None — expired counts as None, and
    the expired entry is dropped on the way out."""
    if not sid:
        return None
    with _lock:
        session = _sessions.get(sid)
        if session is None:
            return None
        if not session.alive():
            _sessions.pop(sid, None)
            return None
        return session


def destroy(sid: str | None) -> None:
    if sid:
        with _lock:
            _sessions.pop(sid, None)


def clear_all() -> None:
    """Forget every session. For tests, and for a restart that must not
    resurrect anything."""
    with _lock:
        _sessions.clear()


def count() -> int:
    with _lock:
        return len(_sessions)


# ------------------------------------------------------------- the cookie
def cookie_value(sid: str) -> str:
    return _serializer().dumps(sid)


def sid_from_cookie(raw: str | None) -> str | None:
    """The id inside a cookie this service signed, or None if it did not."""
    if not raw:
        return None
    try:
        value = _serializer().loads(raw)
    except BadSignature:
        return None
    except Exception:                       # unset secret, malformed payload
        return None
    return value if isinstance(value, str) else None


def attach(response, sid: str) -> None:
    """Put the session cookie on a response.

    Host-only — no `domain` — so it is never sent to Core, which sits on a
    sibling host under the same registrable domain in production. HttpOnly so
    script cannot read it; SameSite=Lax so it survives the redirect back from
    Core's authorize endpoint while not riding on cross-site form posts.
    """
    response.set_cookie(
        config.SESSION_COOKIE,
        cookie_value(sid),
        httponly=True,
        samesite="lax",
        secure=config.on_render(),
        path="/",
    )


def detach(response) -> None:
    response.delete_cookie(config.SESSION_COOKIE, path="/")


def current(request) -> Session | None:
    """The session this request carries, if it still holds."""
    return read(sid_from_cookie(request.cookies.get(config.SESSION_COOKIE)))
