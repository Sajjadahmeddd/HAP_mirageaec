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

Interactive docs at `/docs`.

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
