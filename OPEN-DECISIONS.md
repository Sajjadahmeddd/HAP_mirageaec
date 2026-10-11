# Open decisions

One item. The other ten were MAEC One Core's — the admin panel's badge
vocabulary, the `hidden` access level, session revocation, the login rate
limiter, the per-cell `can()` rule, the account-state enum, the guard's path
exception and the derived control cards — and they moved to the
maec-one-core repository with the code they are about. Nothing was
dropped; look for them there.

What stays is the one that is about *this* repository. It is numbered 11
rather than 1 so that a number means the same decision in either repository.

---

## 11. How does a separated Engineering Tools enforce anything? — decided: b1, then replaced by the gate

**Update (gate-client):** b1 is no longer how this product enforces. Core's
session cookie is now shared across the parent domain, and on every request
Engineering Tools asks Core's `/api/gate/check` who the cookie belongs to.
Core runs its own engine over its own rows and answers with the person's
resolved `permissions` and `nav_hidden`; this product only looks a route's key
up in that list (`backend/maec_auth/gate.py`, `guard.py`).

So the engine no longer runs here, and **the vendored `resolution.py`, its
`resolution.sha256` and the drift test `backend/tests/test_resolution_vendored.py`
are removed**, with the `.gitattributes` lines that pinned them to LF. "One
engine, never two" still holds — more strictly than before: there is one copy
of it, in Core. Core's #18 (vendored, not packaged) no longer has a consumer
in this repository.

The history of b1 follows, unchanged.

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

**Step 1 of it was built here:** `backend/maec_auth/resolution.py` was that
engine, vendored byte-for-byte from Core, with
`backend/tests/test_resolution_vendored.py` failing the moment the copy drifted.
All three are removed now (see the update above).
Why vendored rather than packaged, and what would change that, is Core's #18.

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

## 19. Sessions live in this process — superseded by the gate

This product holds no session any more. The cookie is Core's, the session is
in Core's database, and every request is checked there — so there is nothing
in this process for a second instance or a second worker to be missing. The
in-process store (`session.py`) is removed.

## 20. The API docs need a session, not a permission — decided, still true

`/docs`, `/redoc` and `/openapi.json` enumerate every route, its parameters
and its schema: a map of the API for anyone who asks. They sit behind the gate
like every page: a person MAEC One has signed in, with a seat. They do not
require a permission: a signed-in engineer reading the schema of a route they
may not call learns nothing the UI would not already show them. Pinned by
`test_the_api_docs_need_a_signed_in_person`.

## 21. An expired token is repaired by the browser — superseded by the gate

There is no token. When MAEC One no longer knows the browser (signed out, or
its session ended), the API answers 401 with Core's `login_url`, and the
frontend (`frontend/src/api.js`) sends the window there — once. A mark in
`sessionStorage` survives the trip; a second 401 before `/api/auth/me` has
succeeded shows a message instead of redirecting again, so a refusal cannot
become a loop between two services. Page requests are redirected to
`login_url` by the server itself.
