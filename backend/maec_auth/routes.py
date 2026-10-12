"""/api/auth/me — who the gate says this browser is.

There is no sign-in or sign-out here: both happen at MAEC One Core. By the
time a request reaches this route the gate has already asked Core and put the
answer on `request.state.maec`; this hands the frontend the parts it needs.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from . import config, guard

router = APIRouter(tags=["auth"])


@router.get("/api/auth/me", include_in_schema=False)
def me(request: Request) -> JSONResponse:
    maec = getattr(request.state, "maec", None) or {}
    user = maec.get("user") or {}
    return JSONResponse({
        "authenticated": True,
        "email": user.get("email", ""),
        "name": user.get("name", ""),
        "nav_hidden": list(maec.get("nav_hidden", [])),
        # Which product tabs to render, from nav_hidden and the view permissions.
        "modules": guard.visible_modules(maec),
        # Where "Sign out" goes: signing out at MAEC One signs out everywhere.
        # The browser follows it, so it is Core's public address.
        "core_url": config.core_public_url(),
    }, headers={"Cache-Control": "no-store"})
