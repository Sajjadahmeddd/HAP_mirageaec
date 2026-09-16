# maec_auth

Engineering Tools' half of MAEC One Core's sign-in: an OIDC authorization-code
client, and the vendored engine it enforces with.

| File | What it does |
|---|---|
| `config.py` | The five settings below, from the environment only |
| `verify.py` | Checks a token against Core's JWKS: RS256, kid, iss, aud, exp |
| `routes.py` | `/auth/login` (the one redirect to Core), `/auth/callback`, `/api/auth/me`, `/api/auth/logout` |
| `session.py` | The `et_session` cookie (an id only) and the claims held server-side |
| `guard.py` | Every `/api/*` route: a session, then `resolve` for its permission |
| `resolution.py` | Core's engine, vendored — **never edited here** |

## Configuration

Read from the environment, never a file — this service's one secret is its
client secret, and it must not be committable. With any value missing nobody
can sign in and the API refuses every request (the closed direction); on
Render a missing value refuses the boot.

| Variable | Local value |
|---|---|
| `OIDC_ISSUER` | `http://auth.maec.local:8000` |
| `OIDC_CLIENT_ID` | `engineering-0bef07bb1d6703c4` |
| `OIDC_CLIENT_SECRET` | shown once, when the client was registered in Core |
| `OIDC_REDIRECT_URI` | `http://et.maec.local:8080/auth/callback` — exact, no trailing slash |
| `ET_SESSION_SECRET` | any long random string; signs `et_session` |

Running locally (PowerShell):

```powershell
$env:OIDC_ISSUER="http://auth.maec.local:8000"
$env:OIDC_CLIENT_ID="engineering-0bef07bb1d6703c4"
$env:OIDC_CLIENT_SECRET="<the secret Core showed once>"
$env:OIDC_REDIRECT_URI="http://et.maec.local:8080/auth/callback"
$env:ET_SESSION_SECRET="<any long random string>"
.\.venv\Scripts\python -m uvicorn backend.main:app --host 0.0.0.0 --port 8080
```

Both hostnames need `127.0.0.1` entries in the hosts file, and they must be
two hosts rather than `localhost` twice: cookies are scoped by host, not by
port, so Core's `maec_session` and this product's `et_session` would otherwise
share one jar.

Decisions behind this client: OPEN-DECISIONS #19 (in-process sessions), #20
(the docs need a session), #21 (the browser repairs an expired token).


## resolution.py is vendored. Do not edit it here.

`resolution.py` is a **byte-for-byte copy** of `backend/identity/resolution.py`
in the [maec-one-core](https://github.com/Sajjadahmeddd/maec-one-core)
repository. It is the permission engine both services run: Core builds its
input from database rows, this product builds one from the claims of a token
Core signed (`from_claims`), and then both call the same `resolve()`.

That is the whole point, and it only holds while the two copies are the same
file. If they differ by one line — a tie-break, a level definition, a scope
rule — Core and this product will reach different decisions about the same
token, and nothing will break loudly. It surfaces months later as a
permissions bug nobody can reproduce.

So this copy is not maintained here. It is replaced.

## Updating it

When Core's engine changes:

1. Copy `backend/identity/resolution.py` from Core over this file.
2. Copy `backend/identity/resolution.sha256` alongside it.
3. Run the suite. `backend/tests/test_resolution_vendored.py` must pass.

Never edit `resolution.py` in this repository — not to reformat it, not to fix
an import, not to adapt it. A change that belongs in the engine belongs in
Core, and comes back here through the steps above.

## What the drift test enforces, and what it cannot

`test_resolution_vendored.py` fails if:

* this copy no longer matches the hash beside it (edited or corrupted here);
* it imports anything outside the standard library (a product has to import it
  with no database driver present);
* it no longer decides correctly (an allow and a deny, run through `resolve`).

It **cannot** catch Core changing the engine while nobody re-vendors it here:
this repository has no way to see Core's current hash. Until the two share a
CI that can fetch it, the update ritual above is the only guard. That trigger
is recorded as OPEN-DECISIONS #18.

The hash is taken over the file with CRLF normalised to LF, which is exactly
what Core's `resolution_hash.digest()` does — the same number on either
platform. `.gitattributes` also pins both files to LF so the bytes on disk stay
the bytes that were hashed. The eight-line algorithm is repeated in the test
rather than vendoring Core's `resolution_hash.py`, whose commands and paths
would be wrong here and which can *write* the hash file — something this
repository must never do.
