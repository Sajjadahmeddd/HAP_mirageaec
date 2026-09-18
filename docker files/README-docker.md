# MAEC — Docker deployment

Two images, one origin. Replaces the single Render service.

```
browser ──▶ frontend (nginx :80) ──┬── /            → React bundle (static)
                                   └── /api/*       → backend (uvicorn :8000)
                                        internal docker network, not public
```

The browser still sees **one origin**, so there is no CORS config and no
API base URL to inject — the frontend keeps calling `fetch('/api/...')`
unchanged.

> **v2 — supersedes the earlier README.** That version told you to make a
> code change to `main.py` (already present, and applying it would delete
> the `/assets` mount and the SPA catch-all) and to run
> `cp .env.example .env` (which would overwrite the MAEC One project's
> `.env`). **Do neither.**

---

## No application code changes

`main.py` already guards the bundle mount with `if FRONTEND_DIST.is_dir():`,
so the container path is handled. The real mount is `StaticFiles` at
`/assets` plus a catch-all SPA route — do not replace it with a single
`StaticFiles` at `/`.

Everything below is configuration only.

---

## File placement

```
HAPExt_App/
├── docker-compose.yml               new
├── docker-compose.override.yml      new, optional — laptop-sized limits
├── .dockerignore                    new
├── .env.maec.example                new   (copy to .env.maec)
├── .gitattributes                   new   * text=auto eol=lf
├── Makefile                         new, optional
├── backend/
│   ├── Dockerfile                   new
│   └── docker-entrypoint.sh         new   (must be LF, must be +x)
└── frontend/
    ├── Dockerfile                   new
    ├── nginx.conf                   new
    ├── security-headers.conf        new
    └── .dockerignore                new
```

Two `.gitignore` edits are required:

```
.env.maec                 # ignored already by the existing .env.* rule
!.env.maec.example        # ADD THIS — .env.* would otherwise hide the template
```

---

## Why `.env.maec` and not `.env`

The repository root already has a `.env`, and it belongs to **MAEC One** —
it carries that project's `DATABASE_URL`, `SESSION_SECRET` and
`BOOTSTRAP_ADMIN_PASSWORD`. Pointing `env_file:` at it would inject another
project's database credentials into this container *and* boot the app on
the fallback password committed in `auth.py`.

So this stack reads `.env.maec`, and nothing here ever touches `.env`.

```bash
cp .env.maec.example .env.maec
chmod 600 .env.maec
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # → MAEC_SECRET_KEY
nano .env.maec                                                   # set MAEC_PASSWORD too
```

**`MAEC_SECRET_KEY` is mandatory, not tuning.** `auth.py` falls back to a
random key when it is unset, and that fallback is evaluated *per process*.
With six workers that is six different cookie-signing keys, so roughly five
requests in six fail verification and users are logged out at random. The
container refuses to start without it.

---

## Run it locally first

From the repo root, in WSL:

```bash
docker compose build
docker compose up -d
docker compose ps          # both services should reach "healthy"
```

With `docker-compose.override.yml` present you get 2 workers on modest
limits at **<http://localhost:8080>**; without it, the full production
settings on port 80.

```bash
docker compose logs -f
docker compose down
```

Introspection works normally — the entrypoint passes arguments through:

```bash
docker compose run --rm backend python -c "import pymupdf; print(pymupdf.__version__)"
docker compose run --rm backend id            # must not be uid 0
docker compose run --rm backend sh            # shell in the image
```

And the guard can be proven live:

```bash
docker compose run --rm -e MAEC_SECRET_KEY= backend    # must exit 1, FATAL
```

**Verify parity before trusting it:** run the 212-page DCG BREEZE report
through the container and diff the CSV against the known-good output —
42,391 bytes, 813 rows, matching SHA256. Same engine, same result.

---

## Deploy to the VM

Linux is strongly preferred (see *Host OS* below). On a fresh Ubuntu box:

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER && newgrp docker

git clone git@github.com:mirageaecindia-dev/HAPExt_App.git
cd HAPExt_App

cp .env.maec.example .env.maec && chmod 600 .env.maec
nano .env.maec

docker compose -f docker-compose.yml build      # -f skips the laptop override
docker compose -f docker-compose.yml up -d
```

Updating is three commands, and nothing deploys because someone pushed:

```bash
git pull
docker compose -f docker-compose.yml build
docker compose -f docker-compose.yml up -d
```

Rollback is `git checkout <previous-commit>` and the same two commands.

---

## HTTPS — required before sharing the URL

The stack publishes plain HTTP on :80. These are client drawings; do not
expose that directly. Caddy on the host handles certificates automatically:

```
# /etc/caddy/Caddyfile
engineeringtools.mirageaec.com {
    reverse_proxy localhost:80
}
```

Then firewall :80 to localhost and let Caddy own :443.

**One ordering trap:** `RENDER=1` is set in compose so the session cookie
keeps its `Secure` flag and HSTS stays on. Browsers refuse `Secure` cookies
over plain HTTP on anything other than `localhost` — so on the VM, sign-in
will fail over `http://<raw-ip>` until Caddy is in front. Either bring up
HTTPS in the same session, or drop `RENDER` for the first smoke test and
restore it before anyone else gets the URL.

---

## Host OS

The images are Linux containers and run identically anywhere Docker runs —
Ubuntu, Debian, Rocky, or Windows. **Choose Linux.** On Windows, Linux
containers run inside a WSL2/Hyper-V VM anyway: you pay an extra
virtualisation layer on a CPU- and I/O-bound workload, lose RAM to the VM,
pay Netcup more for the Windows licence, and may hit Docker Desktop's
commercial-use terms. Port 80 is also frequently already held by
`http.sys`/IIS.

Only the host provisioning commands differ; `docker compose build` and
`docker compose up -d` are identical.

---

## Tuning on 8 cores / 16 GB

| Setting | Where | Why |
|---|---|---|
| `WEB_CONCURRENCY=6` | `.env.maec` | Worker **processes**. MuPDF holds the GIL, so threads measure ~1.0× while processes scale. Six leaves headroom for nginx and the OS. |
| `proxy_read_timeout 900s` | `nginx.conf` | The setting Render never exposed. This is what was returning 502 on 40-sheet batches. |
| `client_max_body_size 1G` | `nginx.conf` | nginx defaults to **1 MB**. Deliberately set above the app's own 200 MB per-file limit so FastAPI returns its explained error rather than a bare 413. |
| `tmpfs /tmp/maec-uploads` | `docker-compose.yml` | Uploads in RAM: faster than the overlay filesystem, and they cannot outlive the container. |
| `cpus: "7.0"`, `memory: 12g` | `docker-compose.yml` | Caps the backend so a runaway batch cannot starve nginx or the host. |

Watch a real batch with `docker stats`. If CPU pins near 700% and requests
queue, that is the ceiling — raise `WEB_CONCURRENCY` toward 8 only if
memory allows (roughly 200 MB peak per concurrent parse).

---

## Security headers

`main.py` sets CSP, `X-Content-Type-Options`, `X-Frame-Options`,
`Referrer-Policy` and `Permissions-Policy` on every response it produces.
Once nginx — not FastAPI — serves `index.html`, those no longer reach the
HTML document, so `frontend/security-headers.conf` restates them.

It is `include`d in `location /`, `location = /index.html` and
`location /assets/`, and deliberately **not** at server level or in
`location /api/`: nginx drops inherited `add_header` in any block that
declares one of its own, and `add_header` appends rather than replaces, so
including it on `/api/` would emit duplicates over the backend's own.

If the policy in `main.py` ever changes, change it in both places or the
API and the HTML document will disagree.

---

## Known follow-ups

1. **Rename `RENDER`.** `main.py` keys the `Secure` cookie flag and HSTS on
   a variable called `RENDER`; compose sets it to `1` so those survive the
   move. After the VM deployment is green, rename it to something honest
   (`MAEC_HTTPS`) and delete the compose line — a future maintainer on a
   Netcup box should not find a variable called `RENDER`.
2. **Two failing rebadge tests.** Pre-existing, from commit 975f9d4
   (`sheet_rebadged.pdf` → `sheet.pdf`). Unrelated to Docker; own ticket.
3. **`httpx` is missing**, so `test_backend_api`, `test_backend_auth` and
   `test_backend_headers` cannot collect — the API, auth and header tests
   are not running at all. Add it to a dev/test requirements file, **not**
   `backend/requirements.txt` (it must not enter the production image).

---

## What this does and does not fix

**Fixed:** the 502. You control the proxy timeout now, and six worker
processes handle concurrent batches instead of one.

**Still worth doing:** the 5-pass engine restructure and the TextWriter
change — measured at 2.89–4.19× on real drawings. That speedup is
independent of hosting; it just stops being an emergency.

**Not needed yet:** a database image. The app is genuinely stateless. Add
Postgres when MAEC One brings users, roles and subscriptions — not before.
