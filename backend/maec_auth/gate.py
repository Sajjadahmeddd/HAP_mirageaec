"""The gate: on every request, ask MAEC One Core who this browser is.

Core's session cookie is shared across the parent domain (*.mirageaec.com;
locally *.maec.local), so it arrives here on every request — but it is only a
random id, and the session it names lives in Core's database. So this service
forwards the browser's Cookie header to Core's /api/gate/check, with this
app's key and secret, and acts on the answer:

    200      who the person is and what they may do -> request.state.maec
    401      not signed in   -> /api/*: 401 + Core's JSON; pages: 302 to login_url
    403      no access       -> /api/*: 403 + Core's JSON; pages: a page saying why
    anything else, or no answer within 3 s -> 503. Never let the request through.

Then the route's own permission (guard.py) must be in the person's list.

Nothing is cached: each request asks afresh, so a revoked seat or a sign-out
at Core bites on the very next request.
"""

from __future__ import annotations

import asyncio
import logging
from html import escape

import httpx
from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from . import config, guard

log = logging.getLogger("maec.auth")

TIMEOUT_SECONDS = 3.0

# Answered without asking Core: the bundle's static files and the health probe,
# which must keep answering when Core is down.
EXEMPT = frozenset({"/favicon.png", "/api/health"})
EXEMPT_PREFIXES = ("/assets/",)

UNAVAILABLE = "MAEC One is unavailable"

# What a refusal's reason means to a person reading the 403 page.
REASONS = {
    "no_access": "Your account does not have access to Engineering Tools.",
    "org_suspended": "Your organisation's access to MAEC One is suspended.",
    "bad_origin": "This request did not come from Engineering Tools itself.",
    "bad_app": "Engineering Tools is not set up correctly with MAEC One.",
}

# Tests swap this for an httpx.MockTransport: Core faked in-process.
transport: httpx.AsyncBaseTransport | None = None

# One pooled client per event loop. uvicorn runs one loop per process for its
# lifetime, so in practice this is one client; the loop check only matters
# where loops come and go (the test client), and a pool must not outlive its loop.
_client: httpx.AsyncClient | None = None
_client_loop: asyncio.AbstractEventLoop | None = None


def configure_logging() -> None:
    """Make sure the gate's log is actually emitted under uvicorn.

    uvicorn configures its own loggers and leaves the root logger alone, so
    without this an INFO line (a refused permission) is dropped and only
    WARNINGs escape, via logging's last-resort handler.

    A handler is added only when nothing else is configured to take it;
    where the host already set logging up, that configuration wins and this
    does not double every line. Carried over from main's auth.py.
    """
    log.setLevel(logging.INFO)
    if not log.handlers and not logging.getLogger().handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        log.addHandler(handler)


def exempt(path: str) -> bool:
    return path in EXEMPT or path.startswith(EXEMPT_PREFIXES)


def _http() -> httpx.AsyncClient:
    global _client, _client_loop
    loop = asyncio.get_running_loop()
    if _client is None or _client_loop is not loop:
        _client = httpx.AsyncClient(transport=transport, timeout=TIMEOUT_SECONDS)
        _client_loop = loop
    return _client


def reset_client() -> None:
    """Forget the pooled client, so the next call builds one with the current
    transport. For tests."""
    global _client, _client_loop
    _client, _client_loop = None, None


def original_url(request: Request) -> str:
    """The address the browser actually used, for Core to send it back to.

    Behind Caddy and nginx, request.url is already that address: proxy.py
    applied a trusted proxy's X-Forwarded-Proto and X-Forwarded-Host before
    this ran, and ignored them from anyone else. Core builds the sign-in's
    `next` from this and only follows a `next` on an app's own https://
    address — so a wrong scheme or host here would land people on the
    launcher instead of back in Engineering Tools.
    """
    return str(request.url)


async def ask_core(request: Request) -> httpx.Response:
    """Forward this request's credentials to Core. Raises on no answer."""
    headers = {
        "X-MAEC-App": config.app_key(),
        "X-MAEC-Gate-Secret": config.gate_secret(),
        "X-Original-URL": original_url(request),
        "X-Original-Method": request.method,
    }
    if cookie := request.headers.get("cookie"):
        headers["Cookie"] = cookie
    if origin := request.headers.get("origin"):
        headers["X-Original-Origin"] = origin
    return await _http().get(config.check_url(), headers=headers)


# --------------------------------------------------------------- responses
def _page(title: str, message: str, status: int) -> HTMLResponse:
    """A plain page with a way back to MAEC One. Every value is escaped."""
    try:
        home = config.core_public_url() + "/"
    except config.ConfigError:
        home = ""
    link = f'<a href="{escape(home)}">Back to MAEC One</a>' if home else ""
    body = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{escape(title)}</title>
<style>
 body {{ font: 15px/1.6 system-ui, sans-serif; margin: 12vh auto; max-width: 34rem;
        padding: 0 1.5rem; color: #14204d; background: #f7f7f4; }}
 h1 {{ font-size: 1.35rem; margin-bottom: .4rem; }}
 p  {{ color: #4a4f5e; }}
 a  {{ display: inline-block; margin-top: 1.4rem; padding: .6rem 1.1rem;
       background: #14204d; color: #fff; border-radius: 6px; text-decoration: none; }}
</style></head>
<body><h1>{escape(title)}</h1><p>{escape(message)}</p>{link}</body></html>"""
    return HTMLResponse(body, status_code=status, headers={"Cache-Control": "no-store"})


def _unavailable(is_api: bool) -> Response:
    if is_api:
        return JSONResponse({"detail": UNAVAILABLE}, status_code=503)
    return _page(UNAVAILABLE, "Engineering Tools cannot check who you are right "
                 "now. Try again in a moment.", 503)


def _refused(is_api: bool, status: int, body: dict) -> Response:
    reason = str(body.get("reason", ""))
    login_url = str(body.get("login_url", ""))
    if is_api:
        return JSONResponse({"reason": reason, "login_url": login_url},
                            status_code=status, headers={"Cache-Control": "no-store"})
    if status == 401 and login_url.startswith(("http://", "https://")):
        return RedirectResponse(login_url, status_code=302,
                                headers={"Cache-Control": "no-store"})
    if status == 401:
        return _page("You are not signed in", "Sign in at MAEC One, then come back.", 401)
    return _page("No access", REASONS.get(reason, f"MAEC One refused access ({reason})."), 403)


# -------------------------------------------------------------------- gate
async def inspect(request: Request) -> Response | None:
    """A response to send instead, or None to let the request through."""
    path = request.url.path
    if exempt(path):
        return None
    is_api = path.startswith("/api/")

    try:
        answer = await ask_core(request)
    except config.ConfigError as exc:
        log.error("maec.auth: gate is not configured: %s", exc)
        return _unavailable(is_api)
    except httpx.HTTPError as exc:
        log.warning("maec.auth: MAEC One did not answer the gate check: %r", exc)
        return _unavailable(is_api)

    if answer.status_code in (401, 403):
        try:
            body = answer.json()
        except ValueError:
            body = {}
        if not isinstance(body, dict):
            body = {}
        if body.get("reason") == "bad_app":
            # Our own key or secret is wrong: a deployment fault, not a person's.
            log.error("maec.auth: MAEC One rejected this app's key or gate secret")
        return _refused(is_api, answer.status_code, body)

    if answer.status_code != 200:
        log.warning("maec.auth: gate check answered %s", answer.status_code)
        return _unavailable(is_api)

    try:
        maec = answer.json()
    except ValueError:
        log.warning("maec.auth: gate check answered 200 with no JSON")
        return _unavailable(is_api)
    if not isinstance(maec, dict) or not isinstance(maec.get("permissions"), list):
        log.warning("maec.auth: gate check answered 200 without a permission list")
        return _unavailable(is_api)

    request.state.maec = maec
    return guard.authorize(request, maec)
