"""Proving a token came from Core, unmodified, and was minted for this product.

Everything here fails closed. Each way a token can be wrong raises its own
exception so the log says which, and the caller turns all of them into one
answer for the browser: not authenticated. A verification that cannot be
completed is never a pass.

Keys come from Core's published JWKS and from nowhere else. The URL is built
from OIDC_ISSUER, never from anything inside the token being checked — a token
that could name its own key server would be asking this service to fetch a URL
an attacker chose, against which the forgery would verify perfectly.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import httpx
import jwt

from . import config

log = logging.getLogger("maec.auth")

# Clock skew allowance on exp/iat. Small on purpose: Core's tokens live
# fifteen minutes (Core #16) and both services run on managed clocks.
LEEWAY = 30

# How long a fetched key set is reused. Core sends `Cache-Control: max-age=300`
# and this honours it, with 300s as the floor as well as the usual value — a
# shorter max-age from some proxy should not turn every request into a fetch.
MIN_CACHE_SECONDS = 300

_lock = threading.Lock()
_keys: dict[str, Any] = {}
_fetched_until = 0.0


class TokenRejected(Exception):
    """Base: this token entitles its bearer to nothing here."""


class JwksUnavailable(TokenRejected):
    """Core's keys could not be fetched. Refuse — never assume."""


class KeyUnknown(TokenRejected):
    """The token names a key Core is not publishing, even after a refetch."""


class SignatureRejected(TokenRejected):
    """Checked against Core's key and failed: forged, or altered in flight."""


class ClaimsRejected(TokenRejected):
    """Real signature, wrong token: another audience, another issuer, or past
    its expiry."""


def _max_age(response: httpx.Response) -> int:
    directive = response.headers.get("cache-control", "")
    for part in directive.split(","):
        part = part.strip().lower()
        if part.startswith("max-age="):
            try:
                return int(part.split("=", 1)[1])
            except ValueError:
                break
    return MIN_CACHE_SECONDS


def _fetch() -> None:
    """Replace the cached key set from Core. The caller holds the lock."""
    global _fetched_until
    url = config.jwks_url()
    try:
        response = httpx.get(url, timeout=5.0)
        response.raise_for_status()
        key_set = jwt.PyJWKSet.from_dict(response.json())
    except Exception as exc:
        raise JwksUnavailable(f"could not read {url}: {exc}") from exc

    _keys.clear()
    for key in key_set.keys:
        if key.key_id:
            _keys[key.key_id] = key.key
    _fetched_until = time.monotonic() + max(_max_age(response), MIN_CACHE_SECONDS)
    log.info("maec.auth: fetched %d signing key(s) from %s", len(_keys), url)


def _key_for(kid: str):
    """The public key for this kid, fetching or refetching as needed.

    One refetch on a miss, and one only. Core rotates keys, so an unknown kid
    is first read as "the cache is stale" rather than "forged". A second miss
    is an answer rather than a reason to keep asking — otherwise anyone can
    make this service hammer Core by inventing kids.
    """
    with _lock:
        if not _keys or time.monotonic() >= _fetched_until:
            _fetch()
        if kid in _keys:
            return _keys[kid]
        _fetch()                      # rotated? ask once more, then decide
        if kid in _keys:
            return _keys[kid]
    raise KeyUnknown(f"Core is not publishing a key with kid {kid!r}")


def reset_cache() -> None:
    """Forget the cached keys. For tests, and for a manual rotation."""
    global _fetched_until
    with _lock:
        _keys.clear()
        _fetched_until = 0.0


def verify(token: str) -> dict[str, Any]:
    """The token's claims, or a TokenRejected saying exactly what was wrong.

    In order: a readable header naming a key Core publishes; an RS256
    signature made by that key; `iss` is our issuer; `aud` is this
    application; `exp`/`iat` hold within the leeway.

    The audience is then asserted again on the decoded claims. PyJWT already
    enforced it — this is the one check whose failure hands another
    application's person a working session here, so it does not rest on a
    library option having been passed correctly.
    """
    try:
        header = jwt.get_unverified_header(token)
    except Exception as exc:
        raise SignatureRejected(f"unreadable token header: {exc}") from exc

    kid = header.get("kid")
    if not kid:
        raise KeyUnknown("token header carries no kid")
    if header.get("alg") != "RS256":
        # Named explicitly rather than left to the algorithms list below, so
        # the log says which algorithm was attempted when somebody tries
        # `alg: none` or an HMAC signed with the public key.
        raise SignatureRejected(f"unexpected algorithm {header.get('alg')!r}")

    key = _key_for(kid)
    try:
        claims = jwt.decode(
            token,
            key=key,
            algorithms=["RS256"],
            audience=config.APP_KEY,
            issuer=config.issuer(),
            leeway=LEEWAY,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise ClaimsRejected(f"expired: {exc}") from exc
    except (jwt.InvalidAudienceError, jwt.InvalidIssuerError,
            jwt.MissingRequiredClaimError) as exc:
        raise ClaimsRejected(str(exc)) from exc
    except jwt.InvalidSignatureError as exc:
        raise SignatureRejected(str(exc)) from exc
    except jwt.InvalidTokenError as exc:
        raise SignatureRejected(f"rejected: {exc}") from exc

    if claims.get("aud") != config.APP_KEY:
        raise ClaimsRejected(
            f"audience {claims.get('aud')!r} is not {config.APP_KEY!r}")
    return claims
