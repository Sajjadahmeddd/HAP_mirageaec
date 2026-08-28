"""MAEC web application.

One service: FastAPI serves the API under /api and the built React bundle at
everything else, so there is a single URL and no CORS to configure in
production. In development the Vite dev server proxies /api here, and the
permissive CORS block below only opens when MAEC_DEV is set.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from hap_converter import __version__

from .deps import airsizer_config, hapext_config
from .routers import airsizer, hapext

FRONTEND_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"

app = FastAPI(title="MAEC", version=__version__)

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
