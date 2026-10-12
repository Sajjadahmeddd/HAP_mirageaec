# maec_auth

How Engineering Tools lets MAEC One's signed-in people in. It signs nobody in
itself: MAEC One Core does, and this service asks Core on every request.

| File | What it does |
|---|---|
| `config.py` | The three settings below, from the environment only |
| `gate.py` | Every request: forward the browser's cookie to Core's `/api/gate/check`, act on the answer |
| `guard.py` | The map from each `/api/` route to the permission it needs, checked against Core's list |
| `routes.py` | `/api/auth/me` — who the person is, and which tabs to show |

## How it works

Core's session cookie (`maec_one_session` — not the old app's `maec_session`,
so the two can never be confused) is set for the parent domain —
`.mirageaec.com` in production, `.maec.local` locally — so the browser sends
it here too. It is only a random id; the session lives in Core's database. So
on every request the gate calls Core:

```
GET {CORE_URL}/api/gate/check
  Cookie:             the browser's Cookie header, as received
  X-MAEC-App:         MAEC_APP_KEY
  X-MAEC-Gate-Secret: MAEC_GATE_SECRET
  X-Original-URL:     the full URL the browser asked for
  X-Original-Method:  its method
  X-Original-Origin:  its Origin header, when it has one
```

| Core answers | `/api/*` request | page request |
|---|---|---|
| 200 `{user, org_id, permissions, nav_hidden}` | through, if the route's permission is in `permissions`; else 403 | through |
| 401 `{reason, login_url}` | 401 with the same JSON — the frontend sends the window to `login_url` | 302 to `login_url` |
| 403 `{reason, login_url}` | 403 with the same JSON | a page saying why, with a link back to MAEC One |
| anything else, or nothing within 3 s | 503 "MAEC One is unavailable" | the same, as a page |

Nothing is cached. A revoked seat, or a sign-out at MAEC One, bites on the
very next request.

Not checked with Core: `/assets/*`, `/favicon.png` and `/api/health`.

## Configuration

Read from the environment, never a file. With any of them missing the service
refuses to start, naming what is absent.

| Variable | Value |
|---|---|
| `CORE_URL` | Core's address as this server reaches it. Locally `http://auth.maec.local:8000` |
| `MAEC_APP_KEY` | `engineering` |
| `MAEC_GATE_SECRET` | this app's secret in Core's `GATE_SECRETS` (`engineering=<secret>`) |

Two optional settings:

| Variable | Value |
|---|---|
| `CORE_PUBLIC_URL` | Core as a *browser* reaches it — where "Sign out" and the no-access page link. Unset, it is `CORE_URL`, which is right locally. In the container `CORE_URL` is Docker-internal (`http://maec-core:8000`), so this is `https://auth.mirageaec.com` there. |
| `TRUSTED_PROXIES` | The socket peers whose `X-Forwarded-Proto` and `X-Forwarded-Host` are believed (`proxy.py`); from anyone else they are ignored. Unset trusts nobody. In the container it is the nginx network's range (`maec_et_net`), and never Core's shared network. `*` is refused. |

Behind Caddy and the nginx container the gate sends Core the address the
browser used (`https://engtools.mirageaec.com/...`), not the internal
hop's — Core only follows a sign-in's `next` back to an app's own address.

Running locally (PowerShell):

```powershell
$env:CORE_URL="http://auth.maec.local:8000"
$env:MAEC_APP_KEY="engineering"
$env:MAEC_GATE_SECRET="<the secret in Core's GATE_SECRETS>"
.\.venv\Scripts\python -m uvicorn backend.main:app --host 0.0.0.0 --port 8080
```

Open it at `http://et.maec.local:8080`, never `127.0.0.1`: the cookie is set
for `.maec.local`, and a browser sends it only to hosts under that domain.
Both names need `127.0.0.1` entries in the hosts file.

Core needs, in its `.env`: `SESSION_COOKIE_DOMAIN=.maec.local`,
`CORE_PUBLIC_URL=http://auth.maec.local:8000`, `GATE_SECRETS=engineering=<secret>`
— and the `engineering` application's `base_url` set to
`http://et.maec.local:8080`. Core checks a POST's Origin against it, and only
follows a sign-in's `next` back to an app's own address.
