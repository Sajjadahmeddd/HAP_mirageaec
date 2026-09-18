# MAEC — Docker deployment

Two images, one origin. Replaces the single Render service.

```
browser ──▶ frontend (nginx :80) ──┬── /            → React bundle (static)
                                   └── /api/*       → backend (uvicorn :8000)
                                        internal docker network, not public
```

The browser still sees **one origin**, so there is no CORS config and no API
base URL to inject — the frontend keeps calling `fetch('/api/...')` unchanged.

---

## File placement

Drop these into the repository:

```
HAPExt_App/
├── docker-compose.yml          ← new
├── .dockerignore               ← new
├── .env.example                ← new  (copy to .env on the server)
├── Makefile                    ← new  (optional convenience)
├── backend/
│   └── Dockerfile              ← new
└── frontend/
    ├── Dockerfile              ← new
    ├── nginx.conf              ← new
    └── .dockerignore           ← new
```

Add `.env` to `.gitignore` if it is not there already.

---

## The one code change required

`backend/main.py` currently mounts the built React bundle:

```python
app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="static")
```

In the split deployment nginx serves those files, and `frontend/dist` does
**not** exist inside the backend image — so this line raises at startup and
the container never becomes healthy.

Make the mount conditional. Three lines, and it keeps the single-process
Render/desktop mode working exactly as before:

```python
from pathlib import Path
from fastapi.staticfiles import StaticFiles

_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _dist.is_dir():
    # Single-origin mode (local dev, or the old Render service)
    app.mount("/", StaticFiles(directory=_dist, html=True), name="static")
# In Docker, nginx serves the bundle and this block is simply skipped.
```

Nothing else in the application changes.

---

## Run it locally first (WSL)

From the repo root, inside WSL — not PowerShell, so file permissions and
line endings behave:

```bash
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # paste into MAEC_SECRET_KEY
nano .env                                                        # set MAEC_PASSWORD

docker compose build
docker compose up -d
docker compose ps          # both services should reach "healthy"
```

Then open <http://localhost>. Sign in, convert a real 212-page report, and
rebadge a drawing set. If that works locally it will work on the VM — the
images are identical.

```bash
docker compose logs -f     # watch both services
docker compose down        # stop
```

**Verify parity before trusting it:** run the 212-page DCG BREEZE report
through the container and diff the CSV against the known-good output. It
should be byte-identical — 42,391 bytes, 813 rows. Same engine, same result.

---

## Deploy to the VM

On a fresh Ubuntu box (Netcup, AWS, anywhere):

```bash
# 1. Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER && newgrp docker

# 2. Code
git clone git@github.com:mirageaecindia-dev/HAPExt_App.git
cd HAPExt_App

# 3. Secrets
cp .env.example .env && chmod 600 .env
nano .env

# 4. Go
docker compose build
docker compose up -d
```

Updating later is three commands — and unlike Render, nothing deploys
because someone pushed to `main`:

```bash
git pull
docker compose build
docker compose up -d        # recreates only what changed
```

Rollback is `git checkout <previous-commit>` and the same two commands.

---

## HTTPS

The compose file publishes plain HTTP on :80. Do not expose that to the
internet as-is — these are client drawings. Easiest fix is Caddy on the
host, which obtains and renews certificates automatically:

```
# /etc/caddy/Caddyfile
engineeringtools.mirageaec.com {
    reverse_proxy localhost:80
}
```

Then close :80 to the world and let Caddy own :443. Alternatively point
Cloudflare at the box, or terminate TLS in an AWS load balancer.

---

## Tuning on 8 cores / 16 GB

| Setting | Where | Why |
|---|---|---|
| `WEB_CONCURRENCY=6` | `.env` | Worker **processes**. MuPDF holds the GIL, so threads measure ~1.0× while processes scale. Six leaves headroom for nginx and the OS. |
| `proxy_read_timeout 900s` | `nginx.conf` | The setting Render did not expose. This is what was returning 502 on 40-sheet batches. |
| `client_max_body_size 1G` | `nginx.conf` | nginx defaults to **1 MB** and would reject a drawing set outright. |
| `tmpfs /tmp/maec-uploads` | `docker-compose.yml` | Uploads in RAM: faster than the overlay filesystem, and they cannot outlive the container. |
| `cpus: "7.0"`, `memory: 12g` | `docker-compose.yml` | Caps the backend so a runaway batch cannot starve nginx or the host. |

Watch a real batch with `docker stats`. If CPU pins at 700% and requests
queue, that is the ceiling — raise `WEB_CONCURRENCY` toward 8 only if
memory allows (roughly 200 MB peak per concurrent parse).

---

## What this does and does not fix

**Fixed:** the 502. You now control the proxy timeout, and six worker
processes handle concurrent batches instead of one.

**Still worth doing:** the 5-pass engine restructure and TextWriter change.
They were measured at 2.89–4.19× on real drawings, and that speedup is
independent of hosting — it just stops being an emergency.

**Not needed yet:** a database image. The app is genuinely stateless. Add
Postgres when MAEC One brings users, roles and subscriptions — not before.
