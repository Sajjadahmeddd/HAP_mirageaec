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
from .maec_auth import gate as auth_gate
from .maec_auth import routes as auth_routes
from .routers import airsizer, hapext, rebadge

FRONTEND_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Refuse to start without the three gate settings, and say what this is.

    A service that cannot ask MAEC One who anybody is can only refuse every
    request, so it does not boot at all: `require_all` raises and uvicorn
    exits with the names of what is missing.
    """
    where = "on Render" if os.environ.get("RENDER") else "locally"
    auth_gate.configure_logging()
    auth_config.require_all()
    print(f"Engineering Tools starting {where}.")
    print(f"  auth: gate of {auth_config.core_url()} (app {auth_config.app_key()})")
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
# THE GATE. Engineering Tools signs nobody in; MAEC One Core does.
# ==========================================================================
#
# Core's session cookie is shared across the parent domain, so it arrives on
# every request here. maec_auth/gate.py forwards it to Core's /api/gate/check
# with this app's key and secret, and acts on the answer: 200 lets the request
# through with Core's answer on request.state.maec, 401 sends the person to
# sign in, 403 says no, and no answer is a 503 — never a pass. Then
# maec_auth/guard.py checks the route's own permission against Core's list.
#
# Nothing is cached, so a revoked seat or a sign-out at Core bites on the
# very next request.
#
# Registered below `security_headers` so that one stays outermost and wraps
# the gate's refusals — a refusal carries the same CSP as a page.
# ==========================================================================


@app.middleware("http")
async def gate(request: Request, call_next):
    """Refuse anything from a browser MAEC One has not vouched for."""
    refusal = await auth_gate.inspect(request)
    if refusal is not None:
        return refusal
    return await call_next(request)


# Registered last, so it is the outermost layer and sees every response —
# including the gate's refusals, which return without calling through and so
# never reach anything registered beneath them.
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
        # Which mechanism guards this service: the useful thing to read on a
        # health check. "gate" — every request is checked with MAEC One.
        "auth": "gate",
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
