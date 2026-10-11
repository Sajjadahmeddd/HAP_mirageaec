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

Every request is checked with MAEC One Core, so Core has to be running and the
three gate settings set — see `backend/maec_auth/README.md` for both, and open
the app at `http://et.maec.local:8080`. The Vite dev server below serves the
UI but cannot sign anyone in: the browser holds Core's cookie only for
`.maec.local` hosts, never for `localhost:5173`.

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

## Sign-in — at MAEC One, checked here on every request

Engineering Tools signs nobody in. A person signs in once at MAEC One Core,
whose session cookie is set for the parent domain (`.mirageaec.com`; locally
`.maec.local`) and so reaches this service too. On every request the gate
(`backend/maec_auth/gate.py`) forwards that cookie to Core's
`/api/gate/check` with this app's key and secret, and Core answers: who the
person is and what they may do, or not signed in, or no access. Core
unreachable is a 503 — never a pass. Details: `backend/maec_auth/README.md`.

Each `/api/` route then needs its own permission from the map in
`backend/maec_auth/guard.py`, looked up in the list Core returned. A route with
no entry is refused, and `test_every_product_route_names_a_permission` fails
first.

Nothing is cached, so a revoked seat or a sign-out at MAEC One bites on the
very next request. "Sign out" in the title bar goes to MAEC One: signing out
there signs the person out everywhere.

Not checked with Core: `/assets/*`, `/favicon.png`, and `/api/health`, which
Render probes and which must answer while Core is down.

## Response headers

`SECURITY_HEADERS` in `main.py` bounds what a browser will do with a page we
served. It gates nobody, and is registered **last** so that it wraps every
response — including the gate's refusals, which return without calling
through.

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

Core's business, and documented there. The launcher's tiles come from Core's
`applications` table, the organisation's subscriptions and the person's
licences. An app joins by being under the cookie's domain, having a
`GATE_SECRETS` entry in Core, and running a gate like this one.

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
