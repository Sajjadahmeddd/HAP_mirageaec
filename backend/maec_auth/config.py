"""What the OIDC client reads from the environment, and nothing else.

There is no configuration file here on purpose. Core's `.env` holds database
credentials and signing keys; this service holds one secret — the client
secret it exchanges codes with — and it comes from the environment so it
cannot be committed by accident.

Every accessor raises when its value is missing rather than returning a
default, and they are functions rather than module constants so the app can be
imported (and its tests collected) on a machine with none of them set. Missing
configuration is not an open door: without it no session can ever be created,
and the guard refuses anything without a session.
"""

from __future__ import annotations

import os

# This application's key in Core: the `aud` of every token minted for it, and
# the `app_key` the vendored engine answers questions for. A token carrying
# any other audience is refused in verify.py before the engine ever sees it —
# that is what keeps eight applications on one issuer apart.
APP_KEY = "engineering"

# ET's own session cookie. Deliberately NOT `maec_session`: in production Core
# and this product sit on sibling hosts under one registrable domain, and two
# cookies of the same name on that family are a debugging afternoon nobody
# needs. Host-only, so it is never sent to Core in the first place.
SESSION_COOKIE = "et_session"

# The short-lived cookie carrying `state` from /auth/login to the callback, so
# the callback can prove the browser it is answering is the browser that
# started the flow.
STATE_COOKIE = "et_oidc_state"
STATE_MAX_AGE = 10 * 60          # a sign-in taking longer than this has failed

REQUIRED = (
    "OIDC_ISSUER",
    "OIDC_CLIENT_ID",
    "OIDC_CLIENT_SECRET",
    "OIDC_REDIRECT_URI",
    "ET_SESSION_SECRET",
)


class ConfigError(RuntimeError):
    """A required value is absent. Raised where it is read, never swallowed."""


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(
            f"{name} is not set. Engineering Tools cannot sign anybody in "
            f"without it — backend/maec_auth/README.md lists the five values "
            f"this client needs."
        )
    return value


def issuer() -> str:
    """Core's base URL. The only host this service will fetch keys from."""
    return _required("OIDC_ISSUER").rstrip("/")


def client_id() -> str:
    return _required("OIDC_CLIENT_ID")


def client_secret() -> str:
    """Never logged, never returned, never placed in a redirect. It travels
    only in the body of the server-to-server call to Core's token endpoint."""
    return _required("OIDC_CLIENT_SECRET")


def redirect_uri() -> str:
    """Must match what was registered with Core exactly — Core compares the
    whole string and answers an unregistered one with an error page rather
    than a redirect, which is what stops this becoming an open redirector."""
    return _required("OIDC_REDIRECT_URI")


def session_secret() -> str:
    """Signs this product's own session cookie. Nothing to do with Core's."""
    return _required("ET_SESSION_SECRET")


def jwks_url() -> str:
    return f"{issuer()}/.well-known/jwks.json"


def authorize_url() -> str:
    return f"{issuer()}/oauth/authorize"


def token_url() -> str:
    return f"{issuer()}/oauth/token"


def on_render() -> bool:
    return bool(os.environ.get("RENDER"))


def missing() -> list[str]:
    """Which required values are absent, for the startup banner to name."""
    return [name for name in REQUIRED if not os.environ.get(name, "").strip()]


def require_all() -> None:
    """Refuse to start a deployment that cannot authenticate anybody.

    On Render this raises: a service that boots without its client secret
    serves a sign-in button that can only ever fail, and does it quietly.
    Locally the caller reports instead — a developer working offline should
    get a running process and a clear message, not a traceback at import.
    """
    absent = missing()
    if absent and on_render():
        raise ConfigError(
            "Engineering Tools cannot start: " + ", ".join(absent) +
            " missing from the environment. Set them in the Render dashboard."
        )
