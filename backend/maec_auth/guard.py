"""The gate. What replaced the middleware that left with the identity stack.

Two questions per request, in this order:

  1. Is there a live session? No — 401, and the browser decides whether to
     visit /auth/login. The API never redirects: it is called by fetch, and a
     redirect to Core's HTML sign-in page is not something fetch can follow.
  2. May this person do *this*? Every product route names a permission, and
     the answer comes from the vendored engine reading the token's claims —
     `from_claims` then `resolve`, the same five steps Core runs over its
     database rows. Nothing here re-derives a decision.

**What was lost, and what replaced it.** The old guard read the user's row on
every request, so a suspension or a revoked seat bit on the very next call.
There is no row to read here. The replacement is the token's lifetime: fifteen
minutes (Core #16). A seat revoked in Core keeps working here until the token
expires, and then the silent re-authorization asks Core again and is refused.
That window is the deliberate cost of the split — Core #11 — not an oversight.
"""

from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import JSONResponse

from . import config, session
from .resolution import (
    HIDES_FROM_NAV,
    covers,
    from_claims,
    now,
    resolve,
)

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
    # Neither of these is in the GUARDED list the specification inherited, and
    # both are product routes: preview runs a real rebadge and returns a
    # picture of it, apply writes the whole set. Left unmapped they would have
    # been refused by the default below — but silently, as "unmapped", which
    # is the wrong reason to refuse a route that plainly belongs to a module.
    ("POST", "/api/rebadge/preview"): "engineering:rebadge:view",
    ("POST", "/api/rebadge/apply"): "engineering:rebadge:convert",
}

# Routes carrying a path parameter, matched by prefix.
PREFIXED: tuple[tuple[str, str, str], ...] = (
    ("GET", "/api/airsizer/diagram/", "engineering:airsizer:view"),
)

# Answers to anybody. Exactly one path: the health probe, which Render calls
# without a session and which must keep working when Core is down.
PUBLIC = frozenset({"/api/health"})

# The sign-in flow itself, and the two endpoints that answer for their own
# session. /api/auth/me returning 401 is the frontend's signal to leave.
OPEN_PREFIXES = ("/auth/", "/api/auth/")

# The generated documentation. It enumerates every route, its parameters and
# its schema — a map of the API for anyone who asks. Decided: it needs a
# session, like everything else. It does not need a permission: a signed-in
# engineer reading the schema of a route they may not call learns nothing the
# UI would not show them. Recorded as OPEN-DECISIONS #20.
DOCS = ("/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect")


def permission_for(method: str, path: str) -> str | None:
    """The permission this route requires, or None if it names none."""
    exact = PERMISSIONS.get((method.upper(), path))
    if exact:
        return exact
    for verb, prefix, permission in PREFIXED:
        if method.upper() == verb and path.startswith(prefix):
            return permission
    return None


def needs_session(path: str) -> bool:
    if path in PUBLIC:
        return False
    if path.startswith(OPEN_PREFIXES):
        return False
    return path.startswith("/api/") or path in DOCS


def _refuse(status: int, detail: str) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=status)


def inspect(request: Request) -> JSONResponse | None:
    """A response to send instead, or None to let the request through."""
    path = request.url.path
    if not needs_session(path):
        return None

    live = session.current(request)
    if live is None:
        # Covers both halves of "no session": never had one, and had one whose
        # token has since expired — session.read drops those on the way out,
        # so a stale session is indistinguishable from none here, which is
        # what it should be.
        return _refuse(401, "Sign in required.")
    request.state.session = live

    if path in DOCS:
        return None                      # a session is the whole requirement

    permission = permission_for(request.method, path)
    if permission is None:
        # Default closed. A product route added later without an entry above
        # is refused rather than served, which is the safe direction to get
        # wrong — and it says so in the log rather than failing mutely.
        log.warning("maec.auth: %s %s has no permission mapped; refusing",
                    request.method, path)
        return _refuse(403, "This route is not available.")

    if not resolve(from_claims(live.claims), permission):
        log.info("maec.auth: %s refused %s on %s", live.email, permission, path)
        return _refuse(403, "Your account is not permitted to do this.")
    return None


# ------------------------------------------------------------- navigation
def _hidden_in_nav(data, module: str) -> bool:
    """Does a tool rule take this module out of the navigation?

    `hidden` and `no_access` both do (`HIDES_FROM_NAV`), and they are not the
    same thing: `no_access` is the boundary and `resolve` has already refused
    it, while `hidden` still answers at the API and is only decluttering.
    That distinction is the engine's, and it stays the engine's — this reads
    its table rather than restating which levels mean what.

    Scope is asked with the engine's own `covers` and `Grant.in_force`, so a
    rule attached to a role the person does not effectively hold here cannot
    hide anything from them.
    """
    moment = now()
    reaching = {
        grant.role_id for grant in data.grants
        if grant.in_force(moment)
        and covers(grant, data.org_id, data.app_key, ("application", data.app_key))
    }
    return any(
        level in HIDES_FROM_NAV
        for (rule_module, role_id), level in data.tool_rules.items()
        if rule_module == module and role_id in reaching
    )


def visible_modules(claims: dict) -> dict[str, bool]:
    """Which module tabs to render, per the claims in this session's token.

    A tab is shown when the person may view the module and no rule hides it.
    This is UX and nothing else: the guard's 403 is the boundary, and a tab
    that is hidden here is still refused (or still answered) by `inspect`
    exactly as the engine decides. Keeping the two apart is the point of
    `hidden` existing separately from `no_access` at all.
    """
    data = from_claims(claims)
    return {
        module: bool(resolve(data, f"{config.APP_KEY}:{module}:view"))
        and not _hidden_in_nav(data, module)
        for module in MODULES
    }
