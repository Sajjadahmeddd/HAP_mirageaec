"""MAEC web application.

One service: FastAPI serves the API under /api and the built React bundle at
everything else, so there is a single URL and no CORS to configure in
production. In development the Vite dev server proxies /api here, and the
permissive CORS block below only opens when MAEC_DEV is set.
"""

from __future__ import annotations

import os
from pathlib import Path

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from hap_converter import __version__

from .deps import airsizer_config, hapext_config
from .routers import airsizer, hapext, rebadge

FRONTEND_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Say what this process actually is, which at the moment is unguarded.

    It printed "auth ON" for as long as the identity stack was in this
    process. That stack is MAEC One Core's now, in its own repository and
    its own service, and nothing has taken over from it here — so the honest
    line is the opposite one, printed on every boot, where a quiet start
    would be worse.
    """
    where = "on Render" if os.environ.get("RENDER") else "locally"
    print(f"Engineering Tools starting {where}.")
    print("  !! NO AUTHENTICATION. Every API route answers anybody who can")
    print("  !! reach this address. Sign-in moved to MAEC One Core and the")
    print("  !! OIDC client that replaces it is not built yet. Development")
    print("  !! only — do not deploy this build.")
    yield


app = FastAPI(title="MAEC", version=__version__, lifespan=lifespan)

# What the browser is allowed to do with a page we served. This is not an
# access rule — it gates nothing and no signed-in user can tell it is here.
# It limits the damage if a page ever ends up carrying something it should
# not, which is also why it blocks the "paste this CDN script in" advice
# that circulates for hiding devtools.
#
# Every part of the app is same-origin, so the policy can be tight. The two
# concessions are real needs, not guesses:
#   style-src 'unsafe-inline'  React writes style="" attributes from JSX
#   img-src   blob:            the logo preview in Project Details reads the
#                              chosen file through URL.createObjectURL
#
# frame-ancestors is 'self', not 'none': MAEC One may come to embed its
# modules, and 'none' would break that on the day it does. Other sites are
# still refused, which is what stops our sign-in form being framed over
# someone else's page.
CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self'",
    "connect-src 'self'",
    "form-action 'self'",
    "base-uri 'self'",
    "object-src 'none'",
    "frame-ancestors 'self'",
])

SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",       # no guessing a file's type
    "X-Frame-Options": "SAMEORIGIN",           # for browsers predating CSP
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


# ==========================================================================
# THE GATE WAS HERE. NOTHING HAS REPLACED IT YET.
# ==========================================================================
#
# Two middlewares stood at this point: a guard that refused every /api/*
# call from anyone without a live account — Global Admin for /api/admin/*,
# the CSRF header for admin mutations, a seat on the product for each
# product's routes — and the signed-cookie session it read that account
# from. Both belonged to the identity stack, which is MAEC One Core now, in
# its own repository.
#
# Removing them was right: two copies of one permission engine in two
# repositories drift from the day they exist. It also leaves this service
# open. Every route below answers anybody who can reach the address.
#
# What belongs here instead — and it is deliberately NOT a copy of what was
# removed, because a product must not hold credentials to the identity
# store:
#
#   1. /auth/callback, receiving a one-time code from Core and exchanging
#      it server-to-server for a short-lived JWT scoped to this client.
#   2. Verification of that token against Core's published JWKS —
#      signature, iss, exp, and aud naming *this* application, so a token
#      minted for one of the other seven does not open this one.
#   3. Enforcement from the token's claims. Core stays the only service
#      that reads the identity database.
#
# One property is lost in that move and has to be replaced on purpose,
# not by accident: the old guard re-read the user row on every request, so
# a suspension or a revoked seat bit on the very next call. A token cannot
# do that. The replacement is a short lifetime, and how short IS the
# security decision — OPEN-DECISIONS #11, and the skipped tests in
# tests/test_backend_auth.py that are waiting for the number.
#
# Until all three exist this branch is development-only. Do not merge it and
# do not point a deployment at it.
# ==========================================================================


# Registered last, so it is the outermost layer and sees every response —
# including the guard's 401, which returns without calling through and so
# never reaches anything registered beneath it.
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    for header, value in SECURITY_HEADERS.items():
        response.headers.setdefault(header, value)
    # Only meaningful over TLS, and only true on Render — asserting it in
    # local development would pin a developer's browser to https://localhost.
    if os.environ.get("RENDER"):
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response

if os.environ.get("MAEC_DEV"):
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(hapext.router)
app.include_router(airsizer.router)
app.include_router(rebadge.router)


@app.get("/api/health")
async def health():
    """Readiness: both configs parse and the catalogs are on disk."""
    hapext_config()
    air = airsizer_config()
    return {
        "status": "ok",
        "version": __version__,
        "modules": ["HAPExt", "AirSizer Pro"],
        "diffusers": len(air.diffusers),
        # Was "on", and was true while the guard ran in this process. There
        # is nothing to report as on now, and a health check is the worst
        # place to overstate a protection.
        "auth": "none",
    }



# ---------------------------------------------------------------- frontend
if FRONTEND_DIST.is_dir():
    app.mount(
        "/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets"
    )

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        """Serve the SPA, letting the client router own every non-API path."""
        if full_path.startswith("api/"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")


def run() -> None:
    """Serve the app locally: `python -m backend.main`.

    Render calls uvicorn directly (see render.yaml); this is only so the app
    can be started the same way the desktop one is, without remembering a
    uvicorn incantation.
    """
    import uvicorn

    if not FRONTEND_DIST.is_dir():
        print("frontend/dist is missing — build it first:")
        print("    npm --prefix frontend install")
        print("    npm --prefix frontend run build")
        raise SystemExit(1)

    print("MAEC is running at http://127.0.0.1:8000   (Ctrl+C to stop)")
    uvicorn.run(app, host="127.0.0.1", port=8000, timeout_keep_alive=120)


if __name__ == "__main__":
    run()
