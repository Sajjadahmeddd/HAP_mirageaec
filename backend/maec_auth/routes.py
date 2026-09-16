"""The three edges of the sign-in flow: launch, callback, and who am I.

    /auth/login     the only place that redirects to Core
    /auth/callback  the only place that exchanges a code for a token
    /api/auth/me    what the frontend asks on load; 401 when there is no session
    /api/auth/logout

One redirect origin, deliberately. The callback never bounces back into
/authorize and neither does the guard — they refuse, and the browser decides
whether to visit /auth/login. Two places that can redirect into a sign-in is
how a loop is built: a failure at the callback would send the browser to Core,
which would send it straight back to the callback, which would fail again.
"""

from __future__ import annotations

import logging
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from itsdangerous import BadSignature, URLSafeTimedSerializer

from . import config, guard, session, verify

log = logging.getLogger("maec.auth")

router = APIRouter(tags=["auth"])


def _state_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(config.session_secret(), salt="et-oidc-state")


def _refused(message: str, detail: str = "") -> HTMLResponse:
    """A dead end with a way out, not a redirect.

    Whatever went wrong, the browser is told and left where it is. The link is
    something the person clicks, so a broken sign-in cannot spin between two
    services on its own.
    """
    body = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Sign-in failed</title>
<style>
 body {{ font: 15px/1.6 system-ui, sans-serif; margin: 12vh auto; max-width: 34rem;
        padding: 0 1.5rem; color: #14204d; background: #f7f7f4; }}
 h1 {{ font-size: 1.35rem; margin-bottom: .4rem; }}
 p  {{ color: #4a4f5e; }}
 a  {{ display: inline-block; margin-top: 1.4rem; padding: .6rem 1.1rem;
       background: #14204d; color: #fff; border-radius: 6px; text-decoration: none; }}
</style></head>
<body><h1>{message}</h1><p>{detail}</p>
<a href="/auth/login">Try signing in again</a></body></html>"""
    return HTMLResponse(body, status_code=400)


# ----------------------------------------------------------------- launch
@router.get("/auth/login", include_in_schema=False)
def login() -> RedirectResponse:
    """Start the authorization-code flow at Core.

    `state` is this product's proof that the callback it later answers belongs
    to the browser that started here; `nonce` is its proof that the token it
    receives was minted for this exchange and not replayed from an older one.
    Both are random, both are signed into a short-lived cookie, and both are
    checked at the callback.
    """
    try:
        state = secrets.token_urlsafe(24)
        nonce = secrets.token_urlsafe(24)
        query = urlencode({
            "response_type": "code",
            "client_id": config.client_id(),
            "redirect_uri": config.redirect_uri(),
            "state": state,
            "nonce": nonce,
        })
        target = f"{config.authorize_url()}?{query}"
    except config.ConfigError as exc:
        log.error("maec.auth: cannot start sign-in: %s", exc)
        return _refused("Sign-in is not configured",
                        "This service is missing the settings it needs to talk "
                        "to MAEC One Core. An administrator has to set them.")

    response = RedirectResponse(target, status_code=302)
    response.set_cookie(
        config.STATE_COOKIE,
        _state_serializer().dumps({"state": state, "nonce": nonce}),
        max_age=config.STATE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=config.on_render(),
        path="/",
    )
    return response


# --------------------------------------------------------------- callback
# response_model=None: the return is a redirect on success and an HTML
# page on refusal, and FastAPI would otherwise try to build a response
# model out of that union.
@router.get("/auth/callback", include_in_schema=False, response_model=None)
def callback(request: Request) -> RedirectResponse | HTMLResponse:
    """Core sends the browser back here with a code. Turn it into a session.

    Order matters: the state is checked before anything is exchanged, so a
    code someone else obtained cannot be spent by pointing a victim's browser
    at this URL. Only then does the secret leave this process, and it leaves
    it server-to-server — it is never in a redirect, a response or a log.
    """
    expected = _state_serializer()
    raw_state = request.cookies.get(config.STATE_COOKIE)
    try:
        issued = expected.loads(raw_state or "", max_age=config.STATE_MAX_AGE)
    except (BadSignature, TypeError):
        log.warning("maec.auth: callback with no usable state cookie")
        return _refused("That sign-in could not be completed",
                        "The link was opened without the request this service "
                        "started, or it sat too long before being used.")

    state = request.query_params.get("state")
    if not state or not secrets.compare_digest(state, str(issued.get("state", ""))):
        log.warning("maec.auth: callback state did not match the one issued")
        return _refused("That sign-in could not be completed",
                        "The reply did not match the request this service sent.")

    # Core refuses at its own end — an unentitled person, a suspended
    # organisation — and says so here rather than handing over a code.
    if error := request.query_params.get("error"):
        log.info("maec.auth: Core refused authorization: %s", error)
        return _refused("MAEC One Core did not authorise you for Engineering Tools",
                        "Your account may not hold a seat for this product. "
                        "Ask an administrator to check your access.")

    code = request.query_params.get("code")
    if not code:
        return _refused("That sign-in could not be completed",
                        "Core did not return an authorization code.")

    try:
        exchanged = httpx.post(
            config.token_url(),
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": config.redirect_uri(),
                "client_id": config.client_id(),
                "client_secret": config.client_secret(),
            },
            timeout=10.0,
        )
    except (httpx.HTTPError, config.ConfigError) as exc:
        log.error("maec.auth: token exchange could not be made: %s", exc)
        return _refused("Could not reach MAEC One Core",
                        "The sign-in service did not answer. Try again shortly.")

    if exchanged.status_code != 200:
        # The body can carry Core's reason; the request carried our secret, so
        # only the status and Core's error code are worth writing down.
        log.warning("maec.auth: token exchange refused with %s", exchanged.status_code)
        return _refused("That sign-in could not be completed",
                        "MAEC One Core would not exchange the code. It may "
                        "already have been used, or it may have expired.")

    token = (exchanged.json() or {}).get("access_token")
    if not token:
        return _refused("That sign-in could not be completed",
                        "Core's reply carried no token.")

    try:
        claims = verify.verify(token)
    except verify.TokenRejected as exc:
        log.warning("maec.auth: the token Core returned did not verify: %s", exc)
        return _refused("That sign-in could not be completed",
                        "The token could not be verified against Core's keys.")

    # The nonce ties this token to the launch above: a token minted for an
    # earlier flow, replayed here, carries the wrong one.
    if claims.get("nonce") != issued.get("nonce"):
        log.warning("maec.auth: token nonce did not match the one issued")
        return _refused("That sign-in could not be completed",
                        "The token did not belong to this sign-in.")

    sid = session.create(claims, token)
    response = RedirectResponse("/", status_code=302)
    session.attach(response, sid)
    response.delete_cookie(config.STATE_COOKIE, path="/")
    log.info("maec.auth: signed in %s", claims.get("email", "(no email)"))
    return response


# ------------------------------------------------------------ who am I
@router.get("/api/auth/me", include_in_schema=False)
def me(request: Request) -> JSONResponse:
    """What the frontend asks on load. 401 is the signal to visit /auth/login.

    It answers 401 rather than redirecting because it is called by fetch, and
    a redirect to Core's HTML sign-in page is not something fetch can follow
    usefully. The browser, not the API, decides to leave the page.
    """
    live = session.current(request)
    if live is None:
        return JSONResponse({"authenticated": False}, status_code=401)
    return JSONResponse({
        "authenticated": True,
        "email": live.email,
        "name": live.name,
        "expires_at": live.expires_at,
        # Which product tabs to render. `hidden` is navigation only — the
        # guard still answers those routes — and `no_access` is the boundary;
        # guard.visible_modules keeps that distinction rather than collapsing
        # it here. See OPEN-DECISIONS #3.
        "modules": guard.visible_modules(live.claims),
    })


@router.post("/api/auth/logout", include_in_schema=False)
def logout(request: Request) -> JSONResponse:
    """Forget this browser's session here. Core's own session is untouched —
    signing out of the product is not signing out of the platform."""
    session.destroy(session.sid_from_cookie(request.cookies.get(config.SESSION_COOKIE)))
    response = JSONResponse({"authenticated": False})
    session.detach(response)
    return response
