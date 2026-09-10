"""The rules a change to a person must obey.

No screen calls these yet — the Global Admin screens are the next build.
They exist now so that when those screens arrive they call something that
already refuses the two things that must never happen: an administrator
handing out more than they hold, and the last Global Admin being removed.
Both are enforced here, server-side, whatever the caller looked like.
"""

from __future__ import annotations

import uuid

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Role, RolePermission, User, UserRole
from .permissions import (
    GLOBAL_ADMIN, active_roles, audit, bump_permissions_version, can,
    is_global_admin,
)


class LastGlobalAdminError(Exception):
    """Refused: this would leave the platform with no Global Admin."""


class EscalationError(PermissionError):
    """Refused: the actor tried to grant more than they hold."""


# ----------------------------------------------------- the last admin
def global_admin_holders(db: Session) -> list[User]:
    """Every active account currently holding global_admin at platform."""
    rows = db.scalars(
        select(UserRole).join(Role).where(
            Role.key == GLOBAL_ADMIN, UserRole.scope_type == "platform")).all()
    holders: dict[uuid.UUID, User] = {}
    for grant in rows:
        if grant.expires_at is not None:
            continue
        user = db.get(User, grant.user_id)
        if user is not None and user.status == "active":
            holders[user.id] = user
    return list(holders.values())


def _is_global_admin_grant(grant: UserRole) -> bool:
    return grant.scope_type == "platform" and grant.role.key == GLOBAL_ADMIN


def _would_remove_last_admin(db: Session, user: User) -> bool:
    holders = global_admin_holders(db)
    return len(holders) == 1 and holders[0].id == user.id


# ---------------------------------------------------------------- grants
def _administers(db: Session, actor: User, role: Role,
                 scope_type: str, scope_id: str | None) -> bool:
    """May the actor hand out this role at this scope at all?

    Global Admin may, anywhere. Otherwise the actor needs a role that sits
    above the one being granted and whose own scope contains the target.
    """
    if is_global_admin(db, actor):
        return True
    for held in active_roles(db, actor):
        if held.role.level >= role.level:
            continue
        if held.scope_type == "platform":
            return True
        if held.scope_type == "organization" and held.scope_id == str(actor.org_id):
            return True
        if held.scope_type == "application" and scope_type in ("application", "project"):
            # a lead of an application places people within it; without a
            # project registry the app is the nearest container we can check
            if scope_type == "application" and held.scope_id == scope_id:
                return True
            if scope_type == "project":
                return True
        if held.scope_type == "project" and scope_type == "project" and held.scope_id == scope_id:
            return True
    return False


def grant_role(db: Session, *, actor: User, target: User, role: Role,
               scope_type: str, scope_id: str | None,
               request: Request | None = None) -> UserRole:
    """Give `target` `role` at a scope — if `actor` may.

    Non-escalation, enforced twice: the actor must administer the scope, and
    must themselves hold every permission the role allows, there. Either
    failure is a 403 in the caller and a `blocked` audit row here.
    """
    if target.org_id != actor.org_id and not is_global_admin(db, actor):
        _refuse(db, actor, target, role, scope_type, scope_id, request,
                "actor and target are in different organisations")
    if not _administers(db, actor, role, scope_type, scope_id):
        _refuse(db, actor, target, role, scope_type, scope_id, request,
                "actor does not administer that scope")

    allowed = db.scalars(select(RolePermission).where(
        RolePermission.role_id == role.id, RolePermission.effect == "allow")).all()
    if not is_global_admin(db, actor):
        probe = (scope_type, scope_id) if scope_type != "platform" else None
        for rp in allowed:
            if not can(db, actor, rp.permission.key, probe):
                _refuse(db, actor, target, role, scope_type, scope_id, request,
                        f"actor does not hold {rp.permission.key}")

    grant = UserRole(user_id=target.id, role_id=role.id, scope_type=scope_type,
                     scope_id=scope_id, granted_by=actor.id)
    db.add(grant)
    db.flush()
    bump_permissions_version(db, target.id)
    audit(db, actor=actor, action="role.grant", target_type="user", target_id=target.id,
          result="success", request=request,
          after={"role": role.key, "scope_type": scope_type, "scope_id": scope_id},
          commit=False)
    db.commit()
    return grant


def _refuse(db, actor, target, role, scope_type, scope_id, request, why: str):
    audit(db, actor=actor, action="role.grant", target_type="user", target_id=target.id,
          result="blocked", request=request,
          after={"role": role.key, "scope_type": scope_type, "scope_id": scope_id,
                 "reason": why})
    raise EscalationError(f"Not permitted: {why}.")


def revoke_role(db: Session, *, actor: User, grant: UserRole,
                request: Request | None = None) -> None:
    """Take a grant away — unless it is the last Global Admin's."""
    target = db.get(User, grant.user_id)
    if target is None:
        raise LookupError("no such user")
    if _is_global_admin_grant(grant) and _would_remove_last_admin(db, target):
        audit(db, actor=actor, action="role.revoke", target_type="user",
              target_id=target.id, result="blocked", request=request,
              before={"role": GLOBAL_ADMIN, "scope_type": "platform",
                      "reason": "last global admin"})
        raise LastGlobalAdminError(
            "Cannot remove the last Global Admin. Assign another first.")
    before = {"role": grant.role.key, "scope_type": grant.scope_type,
              "scope_id": grant.scope_id}
    db.delete(grant)
    db.flush()
    bump_permissions_version(db, target.id)
    audit(db, actor=actor, action="role.revoke", target_type="user", target_id=target.id,
          result="success", request=request, before=before, commit=False)
    db.commit()


# ------------------------------------------------------------- the person
def set_user_status(db: Session, *, actor: User, target: User, status: str,
                    request: Request | None = None) -> None:
    if status not in ("active", "suspended", "invited"):
        raise ValueError(f"unknown status {status!r}")
    if status != "active" and _would_remove_last_admin(db, target):
        audit(db, actor=actor, action="user.status", target_type="user", target_id=target.id,
              result="blocked", request=request,
              before={"status": target.status},
              after={"status": status, "reason": "last global admin"})
        raise LastGlobalAdminError(
            "Cannot suspend the last Global Admin. Assign another first.")
    before = {"status": target.status}
    target.status = status
    db.flush()
    bump_permissions_version(db, target.id)
    audit(db, actor=actor, action="user.status", target_type="user", target_id=target.id,
          result="success", request=request, before=before, after={"status": status},
          commit=False)
    db.commit()


def delete_user(db: Session, *, actor: User, target: User,
                request: Request | None = None) -> None:
    if _would_remove_last_admin(db, target):
        audit(db, actor=actor, action="user.delete", target_type="user", target_id=target.id,
              result="blocked", request=request,
              before={"email": target.email, "reason": "last global admin"})
        raise LastGlobalAdminError(
            "Cannot delete the last Global Admin. Assign another first.")
    before = {"email": target.email, "display_name": target.display_name}
    db.delete(target)
    db.flush()
    audit(db, actor=actor, action="user.delete", target_type="user", target_id=target.id,
          result="success", request=request, before=before, commit=False)
    db.commit()
