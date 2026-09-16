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
from .maec_auth import config as auth_config
from .maec_auth import guard
from .maec_auth import routes as auth_routes
from .routers import airsizer, hapext, rebadge

FRONTEND_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Say what this process is, and refuse to be a deployment that cannot.

    For one branch this printed "NO AUTHENTICATION" on every boot, because
    that was true. It is not any more: every route below needs a token MAEC
    One Core signed. What is still worth saying out loud is the configuration,
    because a service missing its client secret can serve a sign-in button
    that only ever fails — on Render `require_all` refuses the boot outright,
    and locally it prints what is absent rather than dying at import.
    """
    where = "on Render" if os.environ.get("RENDER") else "locally"
    auth_config.require_all()
    absent = auth_config.missing()
    print(f"Engineering Tools starting {where}.")
    if absent:
        print("  !! " + ", ".join(absent) + " not set — nobody can sign in.")
        print("  !! The API refuses every request until they are. This is the")
        print("  !! closed direction, not an open one.")
    else:
        print(f"  auth: OIDC client of {auth_config.issuer()} "
              f"(aud {auth_config.APP_KEY})")
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
# THE GATE. Engineering Tools as a client of MAEC One Core.
# ==========================================================================
#
# All three pieces the previous comment specified are here, in maec_auth/:
#
#   1. /auth/callback takes Core's one-time code and exchanges it
#      server-to-server for a short-lived JWT scoped to this client
#      (maec_auth/routes.py). /auth/login is the only place that redirects
#      to Core, so there is one origin for a sign-in and no way to loop.
#   2. maec_auth/verify.py checks that token against Core's published JWKS:
#      RS256 and the header's kid, iss, exp, and aud naming *this*
#      application, so a token minted for one of the other seven does not
#      open this one.
#   3. maec_auth/guard.py enforces from the claims, through the engine
#      vendored from Core — from_claims, then resolve. This service never
#      touches the identity database; Core remains the only one that does.
#
# The property that was lost is still lost, on purpose and not by accident:
# nothing here re-reads a user row, so a suspension or a revoked seat bites
# within the token's fifteen minutes rather than on the next call. That is
# Core #16's number and #11's trade.
#
# Registered below `security_headers` so that one stays outermost and wraps
# the guard's 401 — a refusal carries the same CSP as a page.
# ==========================================================================


@app.middleware("http")
async def gate(request: Request, call_next):
    """Refuse anything from a browser Core has not vouched for.

    Synchronous inside: it reads an in-process dict and runs the engine over
    claims already in memory. There is no database call left to keep off the
    event loop, which is the whole shape of the change.
    """
    refusal = guard.inspect(request)
    if refusal is not None:
        return refusal
    return await call_next(request)


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

app.include_router(auth_routes.router)
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
        # "none" while this branch had no gate at all, and that was the
        # honest word then. It is an OIDC client of Core now — named rather
        # than a bare "on", because which mechanism is guarding a service is
        # the useful thing to read on a health check.
        "auth": "oidc",
    }



# ---------------------------------------------------------------- frontend
if FRONTEND_DIST.is_dir():
    app.mount(
        "/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets"
    )

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        """Serve the SPA, letting the client router own every non-API path.

        The candidate is resolved and checked to be inside the bundle before
        it is served. Without that, `dist / "../../.env"` is a real file and
        this route hands it over: the path comes from the URL, and `..` in a
        URL is not always collapsed by the client that sent it. Core's copy
        of this route was fixed during the extraction; this branch carried
        the original until now.
        """
        if full_path.startswith("api/"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        root = FRONTEND_DIST.resolve()
        candidate = (root / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        return FileResponse(root / "index.html")


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
