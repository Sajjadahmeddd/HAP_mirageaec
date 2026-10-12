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
project's database credentials into this container.

So this stack reads `.env.maec`, and nothing here ever touches `.env`.

```bash
cp .env.maec.example .env.maec
chmod 600 .env.maec
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # → MAEC_GATE_SECRET
nano .env.maec       # the same secret goes into Core's GATE_SECRETS
```

**Sign-in is MAEC One Core's.** Engineering Tools holds no password and no
session: on every request its backend asks Core, over the Docker network,
whether the browser's MAEC One cookie belongs to someone with a seat
(`backend/maec_auth/README.md`). `.env.maec` carries the four settings that
needs — `CORE_URL` (Core inside Docker, `http://maec-core:8000`),
`CORE_PUBLIC_URL` (Core as a browser reaches it), `MAEC_APP_KEY` and
`MAEC_GATE_SECRET` — and the container refuses to start without them. With
no session held here, any number of workers is fine.

This stack joins **Core's** network, `maec_core_net` (external — Core's
compose project creates it), where Core answers as `maec-core`. So **bring
Core's stack up first.** Engineering Tools still starts while Core is stopped
and shows "MAEC One is unavailable"; it cannot start if the network does not
exist at all.

## Running next to the old stack

The gated stack is built to run beside the old Engineering Tools on the same
VPS and collide with none of it. Everything that could clash is set
explicitly in `docker-compose.yml`, with defaults you can override in a `.env`
beside it (documented in `.env.example`):

| | old stack | this stack |
|---|---|---|
| compose project | `maec` | `maec-et` |
| published port | `127.0.0.1:80` | `127.0.0.1:${ET_PORT:-8081}` |
| internal network | `maec_maec_net`, `172.30.57.0/24` | `maec_et_net`, `${ET_NET_SUBNET:-10.231.2.0/24}` |
| MAEC One Core | — | joins `maec_core_net` (external) |

The images are `maec-et-backend` and `maec-et-frontend`, never the old stack's
`maec-backend` / `maec-frontend`: building under those names would retag the
old stack's images, and the next recreate of the old stack — a rollback
included — would start the new code. On Docker's containerd image store an
image whose only tag moves away also drops out of the store, so it cannot
even be tagged back.

**Going live is a Caddy switch:** change `et.mirageaec.com`'s block from
`reverse_proxy localhost:80` to `reverse_proxy localhost:8081` and reload
Caddy. **Rolling back is changing it back.** Neither touches a container.

---

## Run it locally first

From the repo root, in WSL:

```bash
docker compose build
docker compose up -d
docker compose ps          # both services should reach "healthy"
```

The worker count is derived at startup, so there is nothing to tune for a
laptop. It publishes on **<http://localhost:8081>** (`ET_PORT`), so a port 80
already held by IIS, http.sys or another stack is no obstacle. Confirm the
worker count from the startup log:

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
docker compose run --rm -e MAEC_GATE_SECRET= backend   # must exit 1, FATAL
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

The stack publishes plain HTTP on :8081, **bound to 127.0.0.1** — so it is
reachable from the host itself and from nothing else. These are client
drawings; do not expose that directly. Caddy on the host handles
certificates automatically; once this stack is live its block reads:

```
# /etc/caddy/Caddyfile
et.mirageaec.com {
    reverse_proxy localhost:8081    # localhost:80 = the old stack (rollback)
}
```

Caddy then owns :443. The loopback bind in `docker-compose.yml` is what
keeps :8081 private, and it matters more than a firewall rule here: Docker
publishes ports through DNAT rules that are evaluated *before* ufw's, so a
port published as `8081:80` stays reachable from the internet while `ufw
status` still reads "deny". Keep the `127.0.0.1:` prefix on that line.

**One ordering trap:** sign-in needs the real address. MAEC One's cookie is
set for `.mirageaec.com` and is `Secure`, so a browser sends it only to
`https://…mirageaec.com` hosts — over `http://<raw-ip>` nobody is ever
signed in. Bring Caddy up before testing sign-in.

**The scheme reaches the app through two proxies.** Caddy terminates TLS
and sets `X-Forwarded-Proto: https` and `X-Forwarded-Host`; the nginx
container passes both through unchanged (`frontend/nginx.conf`); the app
believes them only when the request's socket peer is in `TRUSTED_PROXIES`,
which compose sets to `maec_et_net`'s fixed range (`backend/maec_auth/proxy.py`;
uvicorn runs with `--no-proxy-headers` so that is the only list). Without all
three links the app thinks it is on `http://`, and Core refuses the
return-after-sign-in address, so people land on the MAEC One launcher instead
of back in Engineering Tools. HSTS follows the same scheme: sent over https,
never on plain http.

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
  - "127.0.0.1:${ET_PORT:-8081}:80"     # not "8081:80"
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

Do **not** substitute `maec-et-frontend:latest` for the throwaway container. Run
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

### Trap 3 — the service refuses to start without MAEC One's settings

`CORE_URL`, `CORE_PUBLIC_URL`, `MAEC_APP_KEY` and `MAEC_GATE_SECRET` are
mandatory, the secret may not be the placeholder, and it must be at least 32
characters (Core refuses anything shorter, which would lock everyone out with
a 403). A missing value is not a warning — the entrypoint exits and the
container does not come up.

```bash
docker compose -f docker-compose.yml logs frontend backend | grep -i fatal
```

Confirm the positive case too, or you have only proven the container is
capable of not starting: open `https://et.mirageaec.com` in a
fresh incognito window. You must be sent to MAEC One's sign-in and, after
signing in, land back in Engineering Tools. If Core is down, every page says
"MAEC One is unavailable" — the gate never lets a request through unchecked.

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
docker run --rm --add-host backend:127.0.0.1 maec-et-frontend:latest nginx -t
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

1. ~~**Rename `RENDER`.**~~ *Resolved on gate-client* — HSTS follows the
   request's scheme (https through a trusted proxy), and compose no longer
   sets `RENDER`.
2. ~~**Two failing rebadge tests.**~~ *Resolved in b6435c9* — the stale
   assertions now expect the source file name.
3. ~~**`httpx` is missing.**~~ *Resolved in 21b38cc* — it lives in
   `requirements-dev.txt`, outside the production image.
4. **AirSizer export fails when the schedule carries a large logo.**
   **Priority: high — a live, user-facing break.** Exporting after loading
   a HAPExt schedule that embeds the 1.23 MB company logo returns 400,
   `Field exceeded maximum size of 1024KB`. Starlette caps every
   *non-file* multipart field at 1 MB, and the browser sends the logo back
   as a base64 data URL (~1.46 MB) inside the `payload` text field.
   Pre-existing: `main` fails identically, so it is not a security-merge
   regression.

   Two ways to fix it, which are not equivalent:
   - **Send the logo as a file part**, as `/api/hapext/download` already
     does. File parts spool to disk and are not subject to that cap, so
     no limit changes. Preferred.
   - **Raise the field cap** for that route. That changes how requests are
     parsed and how much is buffered in memory per field, so it needs its
     own load testing.

   Either way it gets its own testing cycle, not a ride on another change.
   Verify with the end-to-end harness's `air_export_with_logo` case: 400
   today (the positive control), 200 with the logo embedded once fixed.
5. **An interrupted download can leave a scratch folder behind.**
   **Priority: low.** Downloads stream from a scratch folder (`maec_dl_*`,
   `maec_air_*`, `maec_rebadge_*`) that a background task deletes once the
   response finishes. If the browser disconnects first, that task may not
   run, and the folder stays in the temp directory. Flagged in the Step 2
   review; not reproduced yet. The main cost is disk, but the folder also
   keeps a copy of that output on the server until the next restart —
   worth closing for client drawings, even though nothing serves it.

---

## What this does and does not fix

**Fixed:** the 502. You control the proxy timeout now, and six worker
processes handle concurrent batches instead of one.

**Still worth doing:** the 5-pass engine restructure and the TextWriter
change — measured at 2.89–4.19× on real drawings. That speedup is
independent of hosting; it just stops being an emergency.

**Not needed yet:** a database image. The app is genuinely stateless. Add
Postgres when MAEC One brings users, roles and subscriptions — not before.
