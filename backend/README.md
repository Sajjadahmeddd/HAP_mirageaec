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

## Sign-in — there is none, and that is temporary

⚠️ **This service currently has no authentication of any kind.** Every route
under `/api/` answers anybody who can reach the address, and so do `/docs`,
`/redoc` and `/openapi.json`, which map every endpoint and its request shape.
Do not deploy this branch.

It used to say the opposite, and the opposite used to be true:
`backend/identity/` held per-person accounts in PostgreSQL with argon2id
hashes, a guard on every request, per-IP login rate limiting, escalating
lockout and an append-only audit log. All of it now lives in **MAEC One
Core**, in the `maec-one-core` repository and, once deployed, at
`auth.mirageaec.com`. None of it was lost; it stopped being in *this*
process.

Removing it was the point rather than a casualty. Two copies of one
permission engine in two repositories drift from the day they exist, so the
copy had to go before the handoff could be built against one source of truth.

### What replaces it

A person signs in once at Core, opens the Engineering Tools tile, and arrives
here already identified — no second login. Three pieces make that work and
none of them exist yet:

1. **`/auth/callback`** — receives a one-time code from Core and exchanges it
   server-to-server for a short-lived JWT scoped to this application.
2. **Local verification** against Core's published JWKS — signature, `iss`,
   `exp`, and `aud` naming *this* client, so a token minted for one of the
   other seven applications does not open this one.
3. **Enforcement from the token's claims** rather than from a database read.
   Core stays the only service that touches the identity store; Engineering
   Tools never holds credentials to it.

`tests/test_backend_auth.py` carries all three as skipped tests, alongside
the list of product routes that must refuse a stranger — kept verbatim from
when the guard enforced it, because that list is the specification the new
guard inherits.

### The one property that does not survive unchanged

The old guard re-read the user row on **every** request, so a suspension or a
revoked seat took effect on the very next call. A token cannot do that: it is
believed until it expires. The honest replacement is "within the token's
lifetime", which makes **how long that lifetime is** a security decision
rather than a tuning parameter.

It is deliberately not decided here — see `OPEN-DECISIONS.md` #11, which also
weighs the alternative of shipping a copy of the identity package and
connecting to Core's database. That alternative works on day one and is
rejected for a reason worth reading before anyone reaches for it again.

## The launcher

Gone with Core. Signing in used to land on the MAEC One launcher — eight
tiles, one per product — and `Launcher.jsx` went to `maec-one-core` with the
rest of the sign-in surface. Engineering Tools is mounted at the root here
and the title-bar wordmark is a plain mark: it pointed back at the launcher,
and a control that cannot do what it says is worse than no control. It
becomes a link to Core when the handoff lands.

## Response headers

`SECURITY_HEADERS` in `main.py` bounds what a browser will do with a page we
served. It gates nobody, and is registered **last** so that it wraps every
response. That mattered most when it wrapped the guard's 401, which returned
without calling through; with the guard gone these headers are the only
protection on this branch that still works exactly as it always did.

The policy is tight because everything is same-origin. Two concessions are
real needs, not guesses:

| Directive | Why |
|---|---|
| `style-src 'unsafe-inline'` | React writes `style=""` attributes out of JSX |
| `img-src blob:` | the Project Details logo preview reads the chosen file via `URL.createObjectURL` |

`frame-ancestors` is `'self'`, not `'none'`: MAEC One may come to embed its
modules, and `'none'` would forbid that on the day it does. Other origins are
still refused, which is what stops one of our pages being framed over someone
else's.

A CSP fails silently in the console rather than loudly, so changes to it need
driving in a real browser, not just the test client.

## Adding the other MAEC One modules

Core's business now, and documented there. The tile list is computed from the
`applications` table, the organisation's subscriptions and the person's
licences — none of which this service can see any more, which is the whole
point of the split.

⚠️ **Sessions do not cross origins.** A cookie is host-only, so single
sign-on across the eight applications cannot be a shared cookie — that would
scope our session to `.mirageaec.com`, within reach of the marketing site on
the same registrable domain. It is a redirect-based token exchange
(OIDC/JWT) issued by Core, which is the work described under "Sign-in" above.

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
