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
