# Open decisions

Things deliberately left unresolved, with enough context to settle them later
without re-deriving the argument. Nothing here is a bug; each is a choice
waiting on a person — a designer, a manager, or a second application existing.

Add to this file rather than leaving a decision in a commit message or a chat
log, because that is where they get lost.

---

## 1. Badge vocabulary on Roles & Permissions — needs the designer

**Status:** UI correctness. Not a blocker, but it will matter before a client
sees the screen.

The Figma for screen 001 names badges the data model has no concept of:

| Figma says | Exists in the model? |
|---|---|
| View Only | yes, derivable |
| Full Access | yes, derivable |
| Personal Load | **no** |
| Full Team Load | **no** |
| Capacity View | **no** |
| System-wide | **no** |

The last four are resource-planning language. The model is allow/deny over
`app:module:action`, so the screen derives four badges from real rows instead:

    full     every action on that module is allowed
    partial  some are
    view     only `view` is
    none     nothing is

**To settle:** either the designer adopts these four, or the model grows the
concepts the Figma implies — which is a much larger change than a rename, and
should not be done to satisfy a label.

---

## 2. Module names on Tool-Level Settings — needs the designer

**Status:** same category as #1.

The Figma for screen 002 lists rows: *Engineering Workspace, Resource Planner,
Budget Console, Risk Matrix, Executive Dashboard*. None of these exist. The
real permission registry has four modules, seeded and enforced:

    hapext, airsizer, hapaudit, rebadge

The screen reads the registry, so it shows the real four. If those five names
are the intended future product surface, they need to become real applications
and modules first; if they are placeholder art, the Figma should be corrected.

---

## 3. `hidden` has no consumer — needs a decision, then a small change

**Status:** a level an administrator can set that currently does nothing.

Screens 002 distinguishes two restrictive levels, deliberately:

| Level | Navigation | API | Nature |
|---|---|---|---|
| `hidden` | not rendered | still answers | decluttering |
| `no_access` | not rendered | refuses (403) | security boundary |

`no_access` works end to end — `can()` denies, the guard returns 403, tested.

`hidden` does **not**. `permissions.HIDES_FROM_NAV` and the `hides_from_nav`
flag on `GET /api/admin/tool-rules` both exist, but nothing reads them:
Engineering Tools' tab bar does not consult tool rules. So setting a module to
`hidden` today hides nothing and blocks nothing.

That is the exact failure the same screen refuses elsewhere — it rejects a
tool rule that would silently do nothing, on the grounds that a rule which
lies about its effect is worse than no rule. `hidden` is currently such a
rule.

**To settle:** either

* surface the effective hidden modules in `GET /api/auth/me` and have the
  product navigation honour them (small, but it touches Engineering Tools' tab
  bar, which Prompt 2 said not to modify); or
* remove `hidden` from the level list until there is a consumer, leaving
  `no_access` as the only restrictive level.

Doing neither leaves an administrator able to set a control that does nothing.

---

## 4. Are projects shared across applications, or private to each?

**Status:** carried from Prompt 1 §12. Still open, still deliberately unresolved.

If project `P-2291` in Engineering Tools is the same project as `P-2291` in
Timesheet, the project registry belongs in Core. If each application has its
own unrelated notion of a project, they stay local.

Nothing has been built that presumes either answer:

* there is **no `projects` table**;
* `user_roles.scope_id` is an opaque `String(120)`, **not** a foreign key.

One visible consequence today: the seeded test engineer holds `employee` at
**application** scope rather than project scope, because there is no project
registry to name. And `accounts._administers` lets an application-scoped lead
grant at project scope without being able to check *which* projects belong to
their application — that check needs writing the moment projects exist.

---

## 5. Session revocation is bounded by cookie lifetime

**Status:** inherited property of signed-cookie sessions, which Prompt 1
specified. Worth knowing, not currently wrong.

There is no server-side session store, so an individual session cannot be
revoked. A cookie copied before logout stays valid until it expires (12h).

Mitigations already in place: the cookie is `httponly`, `samesite=lax`,
`secure` on Render, and the guard re-reads the user on every request — so
**suspending an account cuts it off on the next call**, which is the practical
kill switch. Rotating `SESSION_SECRET` signs everybody out at once.

**To settle, if it ever matters:** a `session_epoch` column on `users`, bumped
on logout and password change, checked by the guard. That is a schema change,
so it wants doing alongside another migration rather than on its own.

---

## 6. Rate limiting keys on the socket address, which is a proxy on Render

**Status:** needs verifying after the first deploy.

Login is rate limited per IP via `slowapi`'s `get_remote_address`, which reads
the socket peer. Behind Render's proxy that is an internal address shared by
every visitor, so the per-IP limit behaves as a **global** limit — 10 attempts
a minute across the whole company, which would lock everyone out at 9am.

The audit writer already prefers the first `X-Forwarded-For` hop, which is
client-supplied and therefore spoofable.

**To verify after deploying:** sign in, then read `audit_logs.ip`. If it shows
your real public address, forwarding works and only the limiter needs its key
changing. If it shows a `10.x` address, both need it.
