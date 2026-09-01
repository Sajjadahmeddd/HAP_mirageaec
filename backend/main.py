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
from starlette.middleware.sessions import SessionMiddleware

from hap_converter import __version__

from . import auth
from .deps import airsizer_config, hapext_config
from .routers import airsizer, hapext

FRONTEND_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Say plainly whether the service is open, so an unset password on a
    public Render URL cannot pass unnoticed."""
    if auth.is_enabled():
        if not os.environ.get("MAEC_SECRET_KEY"):
            print("MAEC: auth ON, but MAEC_SECRET_KEY is unset — "
                  "everyone is signed out on restart. Set it in Render.")
        else:
            print("MAEC: auth ON (shared account).")
    elif os.environ.get("RENDER"):
        print("MAEC: *** WARNING *** deployed with MAEC_PASSWORD unset — "
              "anyone with the URL can use this app.")
    else:
        print("MAEC: auth OFF (MAEC_PASSWORD unset) — fine for local use.")
    yield


app = FastAPI(title="MAEC", version=__version__, lifespan=lifespan)

# ORDER MATTERS. Starlette runs the *last* middleware added as the outermost
# one, so the guard is registered first and SessionMiddleware second — that
# way the session cookie is decoded before the guard tries to read it.
# Registered the other way round, request.session does not exist yet and
# every request looks signed out.
@app.middleware("http")
async def guard(request: Request, call_next):
    """Refuse API calls from anyone who has not signed in.

    The SPA itself is always served — it has to load in order to show a login
    screen — so only /api/* is gated, minus the login exchange and health.
    """
    if auth.requires_auth(request.url.path) and not auth.is_signed_in(request):
        return JSONResponse({"detail": "Sign in required."}, status_code=401)
    return await call_next(request)


# Signed-cookie sessions: no server-side store, so a Render restart or a
# second instance changes nothing. https_only is off in local development
# because there is no TLS on 127.0.0.1.
app.add_middleware(
    SessionMiddleware,
    secret_key=auth.secret_key(),
    session_cookie="maec_session",
    max_age=auth.SESSION_MAX_AGE,
    same_site="lax",
    https_only=bool(os.environ.get("RENDER")),
)

if os.environ.get("MAEC_DEV"):
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(auth.router)
app.include_router(hapext.router)
app.include_router(airsizer.router)


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
        "auth": "on" if auth.is_enabled() else "off",
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
