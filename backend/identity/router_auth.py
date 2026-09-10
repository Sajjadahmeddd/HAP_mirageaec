"""POST /api/auth/login, POST /api/auth/logout, GET /api/auth/me.

Every outcome of a login attempt is recorded — success, failure, lockout —
with the address that tried and where from, so the audit screen has real
data from the first day.

One message for every failure. Unknown address, wrong password, suspended
account, locked account: the reply is the same and takes the same time, so
nothing about the account list leaks through the login form.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import security
from .db import get_db
from .models import Application, Organization, User
from .permissions import (
    active_roles, audit, current_user, entitled, is_global_admin, now,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Per-IP. The per-account limit is the lockout below; the two together stop
# both a wide guess across many accounts and a deep guess at one.
limiter = Limiter(key_func=get_remote_address)
LOGIN_RATE = "10/minute"

GENERIC_FAILURE = "Incorrect email address or password."

# Escalating lockout. After this many failures the account locks for a
# minute, doubling with each further failure, up to the cap.
LOCK_AFTER = 5
LOCK_BASE = timedelta(minutes=1)
LOCK_CAP = timedelta(minutes=30)


def _lock_for(failures: int) -> timedelta:
    steps = max(0, failures - LOCK_AFTER)
    return min(LOCK_BASE * (2 ** steps), LOCK_CAP)


def _find_user(db: Session, email: str) -> User | None:
    """By (org, email). The org comes from the address's domain; if no
    organisation claims that domain, a unique match on the address alone
    still counts, so a contractor on another domain can be given a seat."""
    domain = email.rsplit("@", 1)[-1] if "@" in email else ""
    org = db.scalar(select(Organization).where(Organization.domain == domain)) if domain else None
    if org is not None:
        found = db.scalar(select(User).where(User.org_id == org.id, User.email == email))
        if found is not None:
            return found
    candidates = db.scalars(select(User).where(User.email == email)).all()
    return candidates[0] if len(candidates) == 1 else None


def _apps_payload(db: Session, user: User | None) -> list[dict]:
    """The catalogue, and — for a signed-in person — what they may open.

    Computed here from subscriptions and seats, never from the client. The
    launcher renders exactly this list.
    """
    out = []
    for app in db.scalars(select(Application).order_by(Application.name)).all():
        item = {"key": app.key, "name": app.name, "description": app.description,
                "status": app.status, "base_url": app.base_url}
        if user is not None:
            item["entitled"] = entitled(db, user, app.key)
        out.append(item)
    return out


def _me_payload(request: Request, db: Session, user: User) -> dict:
    return {
        "authenticated": True,
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "org_id": str(user.org_id),
        "roles": [
            {"role": g.role.key, "scope_type": g.scope_type, "scope_id": g.scope_id}
            for g in active_roles(db, user)
        ],
        "is_global_admin": is_global_admin(db, user),
        "permissions_version": user.permissions_version,
        "apps": _apps_payload(db, user),
        "csrf_token": security.csrf_token(request),
    }


# ------------------------------------------------------------------ routes
@router.get("/me")
def me(request: Request, db: Session = Depends(get_db),
       user: User | None = Depends(current_user)):
    """Drives the frontend: who you are and what you may open — or, before
    signing in, just the catalogue the sign-in screen shows."""
    if user is None:
        return {"authenticated": False, "apps": _apps_payload(db, None)}
    return _me_payload(request, db, user)


@router.post("/login")
@limiter.limit(LOGIN_RATE)
def login(request: Request, payload: dict, db: Session = Depends(get_db)):
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))

    user = _find_user(db, email) if email else None
    moment = now()

    # Verify the hash even when there is no user or the account is locked:
    # every failure path must cost the same as a wrong password.
    hash_ok = security.verify_password(password, user.password_hash if user else None)

    locked = (user is not None and user.locked_until is not None
              and _as_utc(user.locked_until) > moment)
    usable = user is not None and user.status == "active" and not locked

    if not (usable and hash_ok):
        if user is not None:
            user.failed_login_count = (user.failed_login_count or 0) + 1
            newly_locked = False
            if user.failed_login_count >= LOCK_AFTER:
                user.locked_until = moment + _lock_for(user.failed_login_count)
                newly_locked = True
            audit(db, actor=user, action="login.failed", target_type="user",
                  target_id=user.id, source="login", result="warning", request=request,
                  after={"failed_login_count": user.failed_login_count,
                         "locked": locked or newly_locked}, commit=False)
            if newly_locked:
                audit(db, actor=user, action="login.locked", target_type="user",
                      target_id=user.id, source="login", result="blocked",
                      request=request,
                      after={"locked_until": user.locked_until.isoformat()}, commit=False)
            db.commit()
        else:
            audit(db, actor_email=email or None, action="login.failed",
                  target_type="user", target_id=None, source="login",
                  result="warning", request=request)
        raise HTTPException(status_code=401, detail=GENERIC_FAILURE)

    # success
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = moment
    if security.needs_rehash(user.password_hash):
        user.password_hash = security.hash_password(password)
    security.start_session(request, user_id=str(user.id),
                           permissions_version=user.permissions_version)
    audit(db, actor=user, action="login.success", target_type="user", target_id=user.id,
          source="login", result="success", request=request, commit=False)
    db.commit()
    return _me_payload(request, db, user)


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db),
           user: User | None = Depends(current_user)):
    if user is not None:
        audit(db, actor=user, action="logout", target_type="user", target_id=user.id,
              source="api", result="success", request=request)
    security.end_session(request)
    return {"authenticated": False}


def _as_utc(value):
    from datetime import timezone
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
