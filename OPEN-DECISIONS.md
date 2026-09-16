# Open decisions

One item. The other ten were MAEC One Core's — the admin panel's badge
vocabulary, the `hidden` access level, session revocation, the login rate
limiter, the per-cell `can()` rule, the account-state enum, the guard's path
exception and the derived control cards — and they moved to the
maec-one-core repository with the code they are about. Nothing was
dropped; look for them there.

What stays is the one that is about *this* repository, and it is the reason
this branch exists. It is numbered 11 rather than 1 so that the references
to it — in `backend/main.py` where the gate used to be, and in the skipped
tests in `tests/test_backend_auth.py` — keep pointing at the same thing in
both repositories.

---

## 11. How does a separated Engineering Tools enforce anything? — decided: b1

Every enforcement path takes a live `Session` on the identity database:
`can()`, `entitled()`, `is_global_admin()`, `holds_business_admin()`, and the
guard's `inspect()`. That signature assumes Core and the product share a
process. They do today. After the split they share nothing, and the guard
block that enforces entitlement on `/api/hapext/`, `/api/airsizer/` and
`/api/rebadge/` is the only entitlement enforcement those routes have — and
it is in Core, which does not host them.

Stated at length in `EXTRACTION-LOG.md` finding 6b — in the
maec-one-core repository, where that document lives.

**Decided (in maec-one-core, #11): option b1.** Core mints a token; this
product re-runs Core's own five-step engine over its claims, rather than
keeping a copy of the identity package or reaching for Core's database. One
engine, two sources, never two engines.

**Step 1 of it is in this branch:** `backend/maec_auth/resolution.py` is that
engine, vendored byte-for-byte from Core, with
`backend/tests/test_resolution_vendored.py` failing the moment the copy drifts.
Why vendored rather than packaged, and what would change that, is Core's #18.
The rule for updating the copy is `backend/maec_auth/README.md`.

**Option (a): Engineering Tools keeps a copy of `identity/` and connects to
the identity database.**

Works on day one with no new machinery. Costs: the code just extracted into
one place now lives in two repositories and drifts from the first hotfix; and
a product holds credentials to the identity store, which the topology says
applications must never touch. Every future application repeats both costs.

**Option (b): Core mints a signed token; each product verifies it locally and
enforces from its claims.**

The design the architecture implies, and the one that scales to eight
applications. Nothing for it exists yet — no minting, no `aud`, no JWKS
endpoint, no client registration, no rotation. It also needs an answer for
freshness, because the current model's best property is that a suspension or
a revoked seat bites on the *very next request*; a token with any lifetime at
all trades some of that away, and how much is part of this decision.

**What is not in question:** `can()` stays the resolution engine. Under (b)
it grows a sibling that resolves from claims rather than rows, and the two
must share the tie-break rules — one engine with two sources, never two
engines.

**Settle this before Engineering Tools splits, not after.** Nothing signals
it in the meantime: the whole suite passes, because the tests and the engine
are on the same side of the split.

---

Numbering continues Core's sequence (#12–#18 are Core's), so a number means
the same decision in either repository.

## 19. Sessions live in this process — decided, with a follow-up

**Status:** decided with the OIDC client.

The token is ~7.3 kB for a four-role person, past what a cookie may carry, so
it is held on the server and the cookie carries only a signed random id.
Today that server-side store is a dict inside the one running process
(`backend/maec_auth/session.py`).

Right for one instance. **Wrong for two:** a second instance does not know the
first's sessions, so a load balancer alternating requests would send the
person back to Core on every other call. A restart signs everyone out, which
is harmless in practice: the next call re-authorizes silently, because Core's
own session is still valid.

**The follow-up, and its trigger:** the moment Engineering Tools runs more
than one instance, the store moves to Redis or a table. `session.py` already
exposes the interface a shared store implements — `create`, `read`,
`destroy` — so the change is that one file.

## 20. The API docs need a session, not a permission — decided

`/docs`, `/redoc` and `/openapi.json` enumerate every route, its parameters
and its schema: a map of the API for anyone who asks. They sit behind the gate
like every other route. They do not require a permission: a signed-in
engineer reading the schema of a route they may not call learns nothing the UI
would not already show them, and a per-route filter over a generated document
is machinery with no security value. Pinned by
`test_the_api_docs_are_not_readable_by_a_stranger` and
`test_the_api_docs_open_once_signed_in`.

## 21. An expired token is repaired by the browser, not the API — decided (option A)

Tokens live fifteen minutes (Core #16) and there are no refresh tokens. When
one expires mid-use:

* **the API answers 401 and never redirects.** It is called by `fetch`, and a
  302 to Core's HTML sign-in page is nothing `fetch` can use;
* **the frontend** (`frontend/src/api.js`) sends the browser to `/auth/login`.
  Core's own session normally outlives the token, so the round trip returns a
  fresh token with no sign-in screen shown;
* **once.** A mark in `sessionStorage` survives the redirect's page reload; a
  second 401 in the same attempt shows an error with a link instead of
  redirecting again. That is what stops a revoked seat or a suspended
  organisation becoming a loop between two services. A successful
  `/api/auth/me` clears the mark, so a later expiry may re-authorize again.

`/auth/login` is the single place that redirects to Core. The callback never
does and neither does the guard — two redirect origins is how a loop gets
built.

**The cost, stated:** state held in the page is lost across the round trip's
full-page navigation, and the request that failed with the 401 is not replayed;
the user repeats the action. Replaying uploads across a navigation is not
worth its complexity at a fifteen-minute interval — but it is the first thing
to revisit if people report losing work.
