"""What the gate reads from the environment, and nothing else.

Three values, all required. Engineering Tools signs nobody in: MAEC One Core
does, and on every request this service asks Core whether the browser's
cookie belongs to someone who may use it. These are what it needs to ask.

They are functions rather than module constants so the app can be imported
(and its tests collected) on a machine with none of them set. A service
started without them refuses to boot (`require_all`, called at startup); one
that somehow runs without them answers every gated request 503 — closed, not
open.
"""

from __future__ import annotations

import os

REQUIRED = (
    "CORE_URL",
    "MAEC_APP_KEY",
    "MAEC_GATE_SECRET",
)


class ConfigError(RuntimeError):
    """A required value is absent. Raised where it is read, never swallowed."""


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(
            f"{name} is not set. Engineering Tools cannot ask MAEC One who "
            f"anybody is without it — backend/maec_auth/README.md lists the "
            f"three values the gate needs."
        )
    return value


def core_url() -> str:
    """Core's address as this server reaches it, e.g. http://auth.maec.local:8000."""
    return _required("CORE_URL").rstrip("/")


def app_key() -> str:
    """This application's key in Core: `engineering`."""
    return _required("MAEC_APP_KEY")


def gate_secret() -> str:
    """The secret Core holds for this app in GATE_SECRETS. Sent only in the
    server-to-server call to Core — never logged, never returned."""
    return _required("MAEC_GATE_SECRET")


def check_url() -> str:
    return f"{core_url()}/api/gate/check"


def behind_proxy() -> bool:
    """True where this service runs behind a proxy it trusts.

    FORWARDED_ALLOW_IPS is the variable uvicorn itself reads for
    --forwarded-allow-ips; the container sets it to the Docker network's
    range, so it is set exactly where uvicorn is trusting nginx for
    X-Forwarded-Proto. It is the same switch here for X-Forwarded-Host, which
    uvicorn does not read. Unset (a developer's machine), the header is ignored.
    """
    return bool(os.environ.get("FORWARDED_ALLOW_IPS", "").strip())


def on_render() -> bool:
    return bool(os.environ.get("RENDER"))


def missing() -> list[str]:
    return [name for name in REQUIRED if not os.environ.get(name, "").strip()]


def require_all() -> None:
    """Refuse to start without all three. A gate that cannot ask Core can only
    ever refuse, and a service that boots into that state does it quietly."""
    absent = missing()
    if absent:
        raise ConfigError(
            "Engineering Tools cannot start: " + ", ".join(absent) +
            " not set. Set them in the environment that starts uvicorn — "
            "see backend/maec_auth/README.md."
        )
