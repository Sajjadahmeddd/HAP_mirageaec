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
├── docker-compose.override.yml.example  new, optional — local port only
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
nano .env.maec                          # set MAEC_PASSWORD too (min 8 chars)
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

The worker count is derived at startup, so there is nothing to tune for a
laptop. The only local difference is the port: copy
`docker-compose.override.yml.example` to `docker-compose.override.yml` to
serve on **<http://localhost:8080>** instead of 80, which matters when IIS,
http.sys or a system nginx already holds 80. Confirm the worker count from
the startup log:

```bash
docker compose logs backend | head -1
#  MAEC backend: 7 worker process(es) (auto-detected from 8 available CPU(s)), port 8000
```

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

The stack publishes plain HTTP on :80, **bound to 127.0.0.1** — so it is
reachable from the host itself and from nothing else. These are client
drawings; do not expose that directly. Caddy on the host handles
certificates automatically:

```
# /etc/caddy/Caddyfile
engineeringtools.mirageaec.com {
    reverse_proxy localhost:80
}
```

Caddy then owns :443. The loopback bind in `docker-compose.yml` is what
keeps :80 private, and it matters more than a firewall rule here: Docker
publishes ports through DNAT rules that are evaluated *before* ufw's, so a
port published as `80:80` stays reachable from the internet while `ufw
status` still reads "deny". Keep the `127.0.0.1:` prefix on that line.

**One ordering trap:** `RENDER=1` is set in compose so the session cookie
keeps its `Secure` flag and HSTS stays on. Browsers refuse `Secure` cookies
over plain HTTP on anything other than `localhost` — so on the VM, sign-in
will fail over `http://<raw-ip>` until Caddy is in front. Either bring up
HTTPS in the same session, or drop `RENDER` for the first smoke test and
restore it before anyone else gets the URL.

---

## VM day — the traps, and how to prove you avoided them

Every check here comes in two halves: the result you want, and a deliberate
demonstration that the check is capable of producing the other result. A
check that can only pass is not a check. A refused connection proves nothing
on its own — a typo in the address gives you the same refusal, and so does a
host that is simply down. Watch the test fail once, on purpose, and its pass
starts meaning something.

### Trap 1 — Docker publishes ports *past* your firewall

`ufw` is not what keeps :80 private. Docker publishes a port by writing DNAT
rules into the `DOCKER` chain, and those are evaluated **before** the `ufw`
rules. A port published as `80:80` is reachable from the internet while `ufw
status` still reads `deny 80`. This surprises people who did everything
right, and they usually discover it from their access logs.

What closes it is the bind address in `docker-compose.yml`:

```yaml
ports:
  - "127.0.0.1:80:80"     # not "80:80"
```

**Prove it, both ways.** From another machine on the network (or any host
that is not the VM), with `VM` set to the VM's address:

```bash
# 1. the real stack, bound to loopback: must NOT answer
curl -s -m 5 -o /dev/null -w "loopback-bound  -> %{http_code}\n" http://$VM/

# 2. a throwaway container published on ALL interfaces: MUST answer.
#    Run this ON the VM, and remove it the moment you have your answer.
#    nginx:1.27-alpine is already on the host -- it is the frontend image's
#    own runtime base -- and it serves its welcome page with no config of
#    ours involved, which is the point: this half tests the *network path*.
docker run -d --name portproof -p 8097:80 nginx:1.27-alpine
#    then, from the other machine again:
curl -s -m 5 -o /dev/null -w "all-interfaces  -> %{http_code}\n" http://$VM:8097/
docker rm -f portproof          # ON the VM. Do not leave this running.
```

Expect `000` from the first and `200` from the second. If **both** come back
`000`, your test is broken — wrong address, wrong network, host unreachable —
and the first result told you nothing. Only once you have seen `200` from the
second does the `000` from the first mean "bound to loopback".

Do **not** substitute `maec-frontend:latest` for the throwaway container. Run
on its own, outside the compose network, it exits immediately with `host not
found in upstream "backend:8000"` — nginx resolves upstream hostnames at
startup — and you would get `000` from a container that was never listening,
which looks exactly like the result you are trying to distinguish from.

Nothing legitimate loses access: Caddy terminates TLS on the same host and
reaches nginx over loopback.

### Trap 2 — a port scan that never reached the host

```bash
nmap -Pn -p- <vm-ip>          # run from off the box, not on it
```

Wanted: 22, 80 and 443 answer, and nothing else does. But a scan that reaches
nothing at all prints a very similar-looking clean result. Give it the same
positive control: bring `portproof` from Trap 1 back up for a minute, scan
again, and confirm `8097` now shows as open. Once you have watched the scan
*find* a port you deliberately opened, remove the container, scan a third
time, and the quiet result is worth something.

Run the scan from outside the hosting provider's network where you can.
Some providers filter between their own hosts, which makes a scan from a
neighbouring VM look cleaner than the internet's view of the same box.

### Trap 3 — the service now refuses to start without a password

`MAEC_PASSWORD` is mandatory and must be at least 8 characters. There is no
built-in fallback any more, so a missing or short value is not a warning —
the entrypoint exits and the container does not come up. `MAEC_SECRET_KEY`
is mandatory for the same reason (see *Why `.env.maec` and not `.env`*).

```bash
docker compose -f docker-compose.yml logs frontend backend | grep -i fatal
```

Confirm the positive case too, or you have only proven the container is
capable of not starting: sign in once over HTTPS and watch the log line.

```
INFO: sign-in SUCCEEDED at 2026-09-22T07:16:49+00:00: email=... client=...
```

Failed attempts are logged as `WARNING` with the same shape. The password is
never logged, in any form.

### Trap 4 — the laptop override following you to the server

Use `-f docker-compose.yml` on the VM, as the deploy commands above do. It
skips `docker-compose.override.yml`, which publishes 8080 for laptops where
port 80 is already held. The override is gitignored precisely so a server
clone cannot inherit one by accident — but `-f` is what makes that certain.

### Two snags that are not security problems, and will still cost you an hour

**`nginx -t` fails on a built image, outside compose.** The config declares
`upstream maec_backend { server backend:8000; }`, and nginx resolves upstream
hostnames at startup. Outside the compose network there is no `backend`, so
the test reports `host not found in upstream` — which reads exactly like a
broken config and is not one:

```bash
docker run --rm --add-host backend:127.0.0.1 maec-frontend:latest nginx -t
```

**Git Bash on Windows rewrites container paths.** `docker run ... grep -n x
/etc/nginx/conf.d/maec.conf` becomes `C:/Program Files/Git/etc/nginx/...`
before Docker ever sees it, and the error names a path you never typed:

```bash
export MSYS_NO_PATHCONV=1      # then the same command works
```

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

## Tuning

| Setting | Where | Why |
|---|---|---|
| `WEB_CONCURRENCY` *(unset)* | `.env.maec` | Normally left unset. The entrypoint reads the container's cgroup CPU quota — `nproc` reports the **host's** cores and ignores a `--cpus` limit — and starts `cores - 1` worker **processes**, floor 1. MuPDF holds the GIL, so threads measure ~1.0× while processes scale. Set it only to override deliberately. |
| `proxy_read_timeout 900s` | `nginx.conf` | The setting Render never exposed. This is what was returning 502 on 40-sheet batches. |
| `client_max_body_size 1G` | `nginx.conf` | nginx defaults to **1 MB**. Deliberately set above the app's own 200 MB per-file limit so FastAPI returns its explained error rather than a bare 413. |
| `tmpfs /tmp/maec-uploads` | `docker-compose.yml` | Uploads in RAM: faster than the overlay filesystem, and they cannot outlive the container. |
| *(no resource limits)* | `docker-compose.yml` | Deliberately absent. On a single-purpose VM there is nothing to protect the app from, and a hardcoded figure is wrong on any box but the one it was written for. Commented-out stanza is there for the day this host runs other applications too. |

Watch a real batch with `docker stats`. If CPU pins near `(cores - 1) × 100%`
and requests queue, that is the ceiling — raise `WEB_CONCURRENCY` above the
detected value only if memory allows, at roughly 200 MB peak per concurrent
parse.

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
