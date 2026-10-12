#!/bin/sh
# MAEC backend entrypoint.  ->  backend/docker-entrypoint.sh
#
# v4: worker count is DERIVED from the CPU actually available to the
#     container, so the same image runs correctly on a 2-core laptop, a
#     4-core VM or a 16-core box with no configuration change.
#     Set WEB_CONCURRENCY explicitly to override the detection.
set -eu

# --- debugging escape hatch --------------------------------------------
# Any explicit command runs directly, without the server guards:
#   docker compose run --rm backend sh
if [ "$#" -gt 0 ]; then
    exec "$@"
fi

# --- how much CPU do we actually have? ---------------------------------
# nproc reports the HOST's cores and ignores a Docker --cpus limit, so a
# container capped at 2 CPUs on a 16-core host would otherwise start 15
# workers and thrash. Read the cgroup quota first and fall back to nproc
# only when no quota is set.
detect_cpus() {
    # cgroup v2 — "max 100000" means unlimited, "200000 100000" means 2 CPUs
    if [ -r /sys/fs/cgroup/cpu.max ]; then
        read -r _quota _period < /sys/fs/cgroup/cpu.max || true
        if [ "${_quota:-max}" != "max" ] && [ "${_period:-0}" -gt 0 ]; then
            echo $(( (_quota + _period - 1) / _period ))
            return
        fi
    fi
    # cgroup v1
    if [ -r /sys/fs/cgroup/cpu/cpu.cfs_quota_us ] && \
       [ -r /sys/fs/cgroup/cpu/cpu.cfs_period_us ]; then
        _quota=$(cat /sys/fs/cgroup/cpu/cpu.cfs_quota_us)
        _period=$(cat /sys/fs/cgroup/cpu/cpu.cfs_period_us)
        if [ "${_quota}" -gt 0 ] && [ "${_period}" -gt 0 ]; then
            echo $(( (_quota + _period - 1) / _period ))
            return
        fi
    fi
    # No quota — use every core the container can see.
    nproc 2>/dev/null || echo 1
}

if [ -z "${WEB_CONCURRENCY:-}" ]; then
    _cpus=$(detect_cpus)
    # Leave one core for nginx and the OS. Processes, not threads: MuPDF
    # holds the GIL, so threads measure ~1.0x while processes scale.
    if [ "$_cpus" -gt 2 ]; then
        WEB_CONCURRENCY=$(( _cpus - 1 ))
    else
        WEB_CONCURRENCY=1
    fi
    _source="auto-detected from ${_cpus} available CPU(s)"
else
    _source="set explicitly"
fi
export WEB_CONCURRENCY

# --- MAEC One's gate: refuse to start without it -----------------------
# Engineering Tools signs nobody in; every request is checked with MAEC One
# Core. The app itself refuses to start without these; failing here as well
# turns that into one clear line at the top of the container log instead of
# a traceback further down. Set them in .env.maec.
for _name in CORE_URL CORE_PUBLIC_URL MAEC_APP_KEY MAEC_GATE_SECRET; do
    eval "_value=\${${_name}:-}"
    if [ -z "${_value}" ]; then
        echo "FATAL: ${_name} is unset. Set it in .env.maec (see .env.maec.example)." >&2
        exit 1
    fi
done

if [ "${MAEC_GATE_SECRET}" = "generate-on-the-server" ]; then
    echo "FATAL: MAEC_GATE_SECRET is still the placeholder. Generate one on the" >&2
    echo "       server and put the SAME value in Core's GATE_SECRETS:" >&2
    echo '         python3 -c "import secrets; print(secrets.token_urlsafe(32))"' >&2
    exit 1
fi

# Core refuses a gate secret shorter than 32 characters, so this one would
# lock everybody out with a 403 on every request. Say so now instead.
if [ "${#MAEC_GATE_SECRET}" -lt 32 ]; then
    echo "FATAL: MAEC_GATE_SECRET is ${#MAEC_GATE_SECRET} characters; MAEC One" >&2
    echo "       requires at least 32. Generate a new one, in both places." >&2
    exit 1
fi

# --- refuse to start with dev CORS enabled ------------------------------
if [ -n "${MAEC_DEV:-}" ]; then
    echo "FATAL: MAEC_DEV is set. That enables permissive CORS intended" >&2
    echo "       only for the local Vite dev server on port 5173." >&2
    echo "       Unset it before running this container." >&2
    exit 1
fi

# --- the proxy chain: Caddy -> nginx -> here ----------------------------
# Behind Caddy and the nginx container this process sees plain http. With
# --proxy-headers uvicorn takes the scheme from Caddy's X-Forwarded-Proto,
# which nginx passes through -- but only from peers in --forwarded-allow-ips.
# Unset, uvicorn would trust 127.0.0.1 alone, never the nginx container, and
# the app would believe it is on http://: the return-after-sign-in address it
# hands MAEC One Core would then fail Core's check.
if [ -z "${FORWARDED_ALLOW_IPS:-}" ]; then
    echo "FATAL: FORWARDED_ALLOW_IPS is unset. It must be the Docker network's" >&2
    echo "       range (docker-compose.yml sets it to maec_net's subnet)." >&2
    exit 1
fi

echo "MAEC backend: ${WEB_CONCURRENCY} worker process(es) (${_source}), port ${PORT}"
echo "MAEC backend: trusting proxy headers from ${FORWARDED_ALLOW_IPS}"

# uvicorn --workers, not gunicorn: gunicorn's default 30 s worker timeout
# would kill a worker mid-parse on a large drawing set.
exec uvicorn backend.main:app \
    --host 0.0.0.0 \
    --port "${PORT}" \
    --workers "${WEB_CONCURRENCY}" \
    --proxy-headers \
    --forwarded-allow-ips "${FORWARDED_ALLOW_IPS}" \
    --timeout-keep-alive 75
