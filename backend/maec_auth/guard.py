"""May this person do *this*? The map from route to permission.

The gate (gate.py) has already asked MAEC One Core who the browser is, and
put Core's answer on `request.state.maec`, including `permissions`: every
`engineering:<module>:<action>` key the person holds, resolved by Core. This
file only looks the route's key up in that list. It decides nothing itself.
"""

from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.routing import Match

log = logging.getLogger("maec.auth")

# Every module this product offers, for the navigation. HAPAudit is not built
# yet and has no routes; it is listed because Core can already carry rules for
# it and the tab is rendered (disabled) either way.
MODULES = ("hapext", "airsizer", "hapaudit", "rebadge")

# What each route requires. Read as `engineering:<module>:<action>`, the same
# keys Core's registry holds.
#
# The actions are assigned by what the route *does*, not by its HTTP verb:
# reading a schedule into the wizard is `view` however much it POSTs, sizing
# and converting are `convert`, and anything that hands back a built file is
# `export`. That matters because a tool rule of `view` is meant to leave
# somebody able to look without being able to produce.
PERMISSIONS: dict[tuple[str, str], str] = {
    ("GET", "/api/airsizer/config"): "engineering:airsizer:view",
    ("POST", "/api/airsizer/load"): "engineering:airsizer:view",
    ("POST", "/api/airsizer/load-rows"): "engineering:airsizer:view",
    ("POST", "/api/airsizer/size"): "engineering:airsizer:convert",
    ("POST", "/api/airsizer/export"): "engineering:airsizer:export",
    ("POST", "/api/hapext/inspect"): "engineering:hapext:view",
    ("POST", "/api/hapext/inspect-schedule"): "engineering:hapext:view",
    ("POST", "/api/hapext/convert"): "engineering:hapext:convert",
    ("POST", "/api/hapext/download"): "engineering:hapext:export",
    ("POST", "/api/hapext/change-request"): "engineering:hapext:convert",
    ("POST", "/api/rebadge/validate"): "engineering:rebadge:view",
    # Preview runs a real rebadge and returns a picture of it; apply writes
    # the whole set. Both are product routes and both are mapped on purpose.
    ("POST", "/api/rebadge/preview"): "engineering:rebadge:view",
    ("POST", "/api/rebadge/apply"): "engineering:rebadge:convert",
}

# Routes carrying a path parameter, matched by prefix.
PREFIXED: tuple[tuple[str, str, str], ...] = (
    ("GET", "/api/airsizer/diagram/", "engineering:airsizer:view"),
)

# Answers to anybody, without asking Core: the health probe, which must keep
# working when Core is down.
PUBLIC = frozenset({"/api/health"})

# Needs a signed-in person (the gate saw to that) and no particular permission:
# the frontend's "who am I".
OPEN = frozenset({"/api/auth/me"})


def permission_for(method: str, path: str) -> str | None:
    """The permission this route requires, or None if it names none."""
    exact = PERMISSIONS.get((method.upper(), path))
    if exact:
        return exact
    for verb, prefix, permission in PREFIXED:
        if method.upper() == verb and path.startswith(prefix):
            return permission
    return None


# The SPA catch-all (GET /{full_path:path}) matches every GET, including
# /api/... paths, which it answers 404 itself. It is not a product route.
_CATCH_ALL = "/{full_path:path}"


def _a_route_answers(request: Request) -> bool:
    """Does the app have a real route for this method and path?"""
    for route in request.app.router.routes:
        if getattr(route, "path", None) == _CATCH_ALL:
            continue
        if route.matches(request.scope)[0] == Match.FULL:
            return True
    return False


def _refuse(detail: str) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=403)


def authorize(request: Request, maec: dict) -> JSONResponse | None:
    """A 403 to send instead, or None to let the request through.

    Pages, the SPA and the API docs need a signed-in person with a seat — the
    gate's 200 is the whole requirement. Every /api/ route also needs its own
    permission from the map above.
    """
    path = request.url.path
    if not path.startswith("/api/") or path in PUBLIC or path in OPEN:
        return None

    permission = permission_for(request.method, path)
    if permission is None:
        if not _a_route_answers(request):
            # No route at all for this method and path: let the app say so,
            # exactly as the live app does - 405 for a wrong method on a real
            # path, 404 for a path that does not exist. Nothing is served.
            return None
        # Default closed. A real product route added later without an entry
        # above is refused rather than served, and says so in the log.
        log.warning("maec.auth: %s %s has no permission mapped; refusing",
                    request.method, path)
        return _refuse("This route is not available.")

    if permission not in maec.get("permissions", ()):
        email = (maec.get("user") or {}).get("email", "?")
        log.info("maec.auth: %s refused %s on %s", email, permission, path)
        return _refuse("Your account is not permitted to do this.")
    return None


def visible_modules(maec: dict) -> dict[str, bool]:
    """Which module tabs to render: the person may view the module and Core's
    `nav_hidden` does not leave it out. Navigation only — the 403 above is the
    boundary, and a hidden module's routes still answer if permitted."""
    permissions = set(maec.get("permissions", ()))
    hidden = set(maec.get("nav_hidden", ()))
    return {
        module: f"engineering:{module}:view" in permissions and module not in hidden
        for module in MODULES
    }
