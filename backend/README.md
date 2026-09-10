# MAEC web

The same two modules as the desktop app, over HTTP. FastAPI serves the API
under `/api` and the built React bundle at everything else.

## The one rule

**The engine is not touched.** `backend/` imports `hap_converter.engine` and
`hap_converter.airsizer.engine` exactly as the PySide6 window does, and every
route is a thin wrapper around the same function. The desktop app still
builds and its 137 tests still pass — the web app is additive.

What the port replaces is only the UI layer:

| Desktop | Web |
|---|---|
| PySide6 windows / widgets | React components |
| `QFileDialog` local paths | browser upload / download |
| `QThread` + Qt signals | one HTTP request + a loading state |
| staged file in `%LOCALAPPDATA%` | rows held in the browser, file rebuilt on download |

## Run it locally

Two terminals, from the repo root:

```powershell
# API
.\.venv\Scripts\python -m uvicorn backend.main:app --reload --port 8000

# UI (proxies /api to :8000)
npm --prefix frontend install
npm --prefix frontend run dev
```

Then open <http://localhost:5173>.

For a production-shaped run, build the bundle once and let FastAPI serve it:

```powershell
npm --prefix frontend run build
.\.venv\Scripts\python -m uvicorn backend.main:app --port 8000
```

<http://localhost:8000> now serves the whole app.

## Endpoints

| Method | Path | Wraps |
|---|---|---|
| POST | `/api/hapext/inspect` | page count for the upload card |
| POST | `/api/hapext/convert` | `engine.pipeline.convert` |
| POST | `/api/hapext/download` | `synthesizer.build_project_header` / `xlsx_exporter.write_fcu_xlsx` |
| POST | `/api/hapext/inspect-schedule` | `change_request.load_schedule` |
| POST | `/api/hapext/change-request` | `engine.pipeline.convert_change_request` |
| GET | `/api/airsizer/config` | `airsizer.engine.config.load` |
| GET | `/api/airsizer/diagram/{key}` | the construction drawing PNG |
| POST | `/api/airsizer/load` | `airsizer.pipeline.load_spaces` |
| POST | `/api/airsizer/load-rows` | same, from a HAPExt run already in the browser |
| POST | `/api/airsizer/size` | `airsizer.pipeline.size_space` |
| POST | `/api/airsizer/export` | `airsizer.export.write_xlsx` |

| POST | `/api/rebadge/validate` | `rebadger.pipeline.check` per sheet |
| POST | `/api/rebadge/preview` | `rebadger.pipeline.preview` — a PNG of the real edit |
| POST | `/api/rebadge/apply` | `rebadger.pipeline.rebadge_batch` + audit |

Interactive docs at `/docs`.

## PDF Rebadging

Retitles CAD drawing sheets: PROJECT STAGE and SHEET STATUS are replaced in
place, a row is appended to the revision history, and the bottom-right
REVISION cell is overwritten. The drawing itself is never edited.

Two rules shape the engine:

- **Redaction, not cover-up.** Old values leave the content stream via
  redaction annotations, and removal is verified by re-extracting the region.
  A white box over old text would leave it selectable and searchable, which on
  a revision-controlled drawing is worse than not editing at all.
- **Label-anchored geometry.** Cells are found from the printed labels and the
  ruled lines, never fixed coordinates, so one implementation handles both
  frames the exports use: a portrait media box displayed rotated 90°, and a
  native landscape page. They print identically and share no raw coordinates.

⚠️ Rewriting a content stream is the one thing that could disturb the drawing,
so `verify.py` compares every span's position before and after and reports
anything that moved outside the edited cells. On one of the five samples
MuPDF's rewriter shifts a single annotation by 4.8 pt; that sheet is emitted
with a named warning rather than silently. See the module summary for the
open question about whether that should fail the sheet instead.

## Sign-in

A Render service has a **public URL**, so without a gate anyone holding the
link could upload reports and pull schedules. `backend/identity/` closes
that, and **signing in is always required** — there is no configuration that
leaves the app open.

Accounts are per person, held in PostgreSQL, with argon2id password hashes.
There is no shared credential and no built-in fallback account: an
unseeded database means nobody can sign in, which is the safe direction.

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL. `postgresql+psycopg://user:pass@host:5432/db` |
| `SESSION_SECRET` | Signs the session cookie. Changing it signs everyone out. |
| `BOOTSTRAP_ADMIN_EMAIL` | The first Global Admin, created by the seed. |
| `BOOTSTRAP_ADMIN_PASSWORD` | That account's password. Minimum 12 characters. |
| `SEED_TEST_USER_EMAIL` | An ordinary engineer, for testing the non-admin path. |
| `SEED_TEST_USER_PASSWORD` | Set **both** or neither — unset means no test account. |

`.env` is read at startup and is gitignored; a real environment variable
always wins over the file, so Render (which has no `.env`) is unaffected.
`MAEC_SECRET_KEY` is still honoured as a fallback for `SESSION_SECRET` so an
existing Render value keeps working.

### Setting up locally

```powershell
# once: create the database
createdb -U postgres maec_identity

# schema
.\.venv\Scripts\python -m alembic -c backend/identity/alembic.ini upgrade head

# people, products, roles and permissions — safe to re-run
.\.venv\Scripts\python -m backend.identity.seed
```

The seed is idempotent: it looks every row up by its natural key before
creating it, so a second run reports "nothing to do". Re-running it with a
different `BOOTSTRAP_ADMIN_PASSWORD` resets that password, which is how a
lost admin account is recovered without opening psql.

To add a migration after changing `models.py`:

```powershell
.\.venv\Scripts\python -m alembic -c backend/identity/alembic.ini revision --autogenerate -m "what changed"
```

**Read the generated file before applying it.** Autogenerate cannot see
triggers, and the initial migration carries one: `audit_logs` has a
`BEFORE UPDATE OR DELETE` trigger that raises, so the append-only rule is
enforced by the database and not merely by convention.

### What is enforced, and where

Everything under `/api/` is guarded except `/api/auth/*` and `/api/health`,
so a route added for a new module is protected without touching the guard.
`identity/guard.py` holds the rules and runs on every request:

- a session that resolves to an **active** user — read from the database each
  time, so a suspension bites on the next request rather than at cookie
  expiry;
- `/api/admin/*` additionally requires **Global Admin**, and any mutation
  there requires the CSRF header;
- each product's routes require a **seat** on that product, so an unlicensed
  person gets a 403 whatever the frontend rendered.

`/docs`, `/redoc` and `/openapi.json` sit outside `/api/` and are named
explicitly: they map every endpoint and its request shape, so they are gated
rather than public. The SPA shell itself is always served — it has to load in
order to show a login screen at all.

Login is rate limited per IP, and an account locks for escalating periods
after repeated failures. Every outcome — success, failure, lockout, logout —
writes an `audit_logs` row with the address, the IP and the user agent. A
failure always returns the same message and takes the same time, whether the
address is unknown, the password wrong, or the account suspended or locked.

The session is a **signed cookie**, not a server-side store, so it survives a
restart or a second instance with no shared state. It is `httponly`,
`samesite=lax`, `secure` on Render, and deliberately carries **no `domain`
attribute**: the company site shares the registrable domain
(`mirageaec.com`), and a cookie scoped to `.mirageaec.com` would place our
session inside its reach.

⚠️ **Middleware order matters.** The guard is registered *before*
`SessionMiddleware` so that Starlette runs the session decoder first.
Registered the other way round, `request.session` does not exist when the
guard reads it and every request looks signed out.

## The launcher

Signing in lands on the MAEC One launcher, not inside a module. It is the
same frame as the sign-in screen — `MaecOne.jsx`, shared by both — with the
right-hand panel swapped and the eight tiles turned into controls.

`READY` in `Launcher.jsx` is the whole release gate: it lists the module keys
that can be opened, and every other tile shows "Coming soon". As each of the
other seven products is built, add its key there and its tile turns on.

The wordmark in the title bar goes back to the launcher, so a module is never
a dead end. Signing out and a lapsed session both return there too, so the
next sign-in never drops you straight back inside a module.

## Response headers

`SECURITY_HEADERS` in `main.py` bounds what a browser will do with a page we
served. It gates nobody — a signed-in user cannot tell it is there — and is
registered **last**, so it wraps every response including the guard's 401,
which returns without calling through.

The policy is tight because everything is same-origin. Two concessions are
real needs, not guesses:

| Directive | Why |
|---|---|
| `style-src 'unsafe-inline'` | React writes `style=""` attributes out of JSX |
| `img-src blob:` | the Project Details logo preview reads the chosen file via `URL.createObjectURL` |

`frame-ancestors` is `'self'`, not `'none'`: MAEC One may come to embed its
modules, and `'none'` would forbid that on the day it does. Other origins are
still refused, which is what stops the sign-in form being framed over someone
else's page.

A CSP fails silently in the console rather than loudly, so changes to it need
driving in a real browser, not just the test client.

## Adding the other MAEC One modules

The tile list is **no longer a constant in the frontend**. `GET /api/auth/me`
returns the catalogue, computed from the `applications` table, the
organisation's `subscriptions` and the person's `user_licenses`. A tile is
openable only when the product is `live`, the person holds a seat, and there
is a `base_url` to send them to — and the API refuses the request
independently, so a tile is a convenience rather than the gate.

To bring a product online: deploy it, set its `applications.base_url` and
`status = 'live'`, then give people seats. Nothing is rebuilt.

⚠️ **Sessions do not cross origins.** The cookie is host-only, so a user sent
to another service is asked to sign in again. Single sign-on across the eight
is a redirect-based token exchange (OIDC/JWT) issued by MAEC One Core once it
is a service of its own at `auth.mirageaec.com` — deliberately not a cookie
shared across subdomains, which would put our session in reach of the
marketing site on the same registrable domain.

## Statelessness

Render's disk is ephemeral, so nothing is kept between requests:

- an upload is written to a temp file, passed to the engine as a path, and
  deleted in a `finally` (or a `BackgroundTask` when the file is being
  streamed back);
- `config/` — `mapping.json`, `input_matrix.json`, the five catalogs and the
  five diagrams — ships in the repo as read-only assets, exactly as it does
  on the desktop. That is configuration, not storage;
- a sizing session lives in React state for the life of the browser tab.

**Known v1 limitation:** Save Project / Recent Projects are not wired to any
server-side store. The desktop keeps sizing sessions in `%APPDATA%`;
`airsizer/engine/project.py` is still present and still tested, just not
reachable from the web UI. A sizing run is expected to finish in one sitting
and the exported workbook is the artifact. Reloading the tab starts over.

## Deploying without Node

`render.yaml` builds the frontend during deploy. If the runtime you pick has
no Node, build `frontend/dist` locally, commit it, and shorten the build to:

```yaml
buildCommand: pip install -r backend/requirements.txt
```

`backend/main.py` serves whatever `frontend/dist` contains; it does not care
who built it.

## Long requests

A 212-page report parses in about 0.8 s server-side, so the single
synchronous request in §7 of the migration brief is comfortable. The start
command raises `--timeout-keep-alive` to 120 s for headroom on a much larger
report. If a report ever does time out, add a job-id + polling endpoint —
not a task queue.
