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

# --- MAEC_SECRET_KEY is load-bearing under multi-worker ----------------
# auth.py falls back to secrets.token_urlsafe(32) when this is unset, and
# that fallback is evaluated PER PROCESS. With more than one worker each
# signs session cookies with a different key, so most requests fail
# verification and users are bounced to the login screen at random.
if [ -z "${MAEC_SECRET_KEY:-}" ] || \
   [ "${MAEC_SECRET_KEY}" = "generate-a-long-random-value" ]; then
    echo "FATAL: MAEC_SECRET_KEY is unset or still the placeholder value." >&2
    echo "       With more than one worker this causes random logouts," >&2
    echo "       because each worker process would sign cookies with a" >&2
    echo "       different randomly-generated key." >&2
    echo "" >&2
    echo "       Generate one:" >&2
    echo '         python3 -c "import secrets; print(secrets.token_urlsafe(48))"' >&2
    echo "       Then set MAEC_SECRET_KEY in .env.maec" >&2
    exit 1
fi

# --- warn if the gate is running on fallback credentials ---------------
if [ -z "${MAEC_PASSWORD:-}" ]; then
    echo "WARNING: MAEC_PASSWORD is unset — the app will use the fallback" >&2
    echo "         password committed in backend/auth.py, which is readable" >&2
    echo "         by anyone with repository access. Set it in .env.maec." >&2
fi

# --- refuse to start with dev CORS enabled ------------------------------
if [ -n "${MAEC_DEV:-}" ]; then
    echo "FATAL: MAEC_DEV is set. That enables permissive CORS intended" >&2
    echo "       only for the local Vite dev server on port 5173." >&2
    echo "       Unset it before running this container." >&2
    exit 1
fi

echo "MAEC backend: ${WEB_CONCURRENCY} worker process(es) (${_source}), port ${PORT}"

# uvicorn --workers, not gunicorn: gunicorn's default 30 s worker timeout
# would kill a worker mid-parse on a large drawing set.
exec uvicorn backend.main:app \
    --host 0.0.0.0 \
    --port "${PORT}" \
    --workers "${WEB_CONCURRENCY}" \
    --timeout-keep-alive 75
