#!/bin/sh
# MAEC backend entrypoint.  ->  backend/docker-entrypoint.sh
#
# v3: arguments are passed through, so the image behaves conventionally.
#     `docker compose run --rm backend python -c "..."` runs python;
#     `docker compose run --rm backend id` runs id; with no arguments the
#     startup guards run and the server starts. Previously any argument
#     was silently ignored and uvicorn started regardless.
set -eu

# --- debugging escape hatch --------------------------------------------
# Any explicit command runs directly, without the server guards. This is
# what makes introspection work:  docker compose run --rm backend sh
if [ "$#" -gt 0 ]; then
    exec "$@"
fi

# --- MAEC_SECRET_KEY is load-bearing under multi-worker ----------------
# auth.py falls back to secrets.token_urlsafe(32) when this is unset, and
# that fallback is evaluated PER PROCESS. With WEB_CONCURRENCY=6 each
# worker signs session cookies with a different key, so roughly five
# requests in six fail verification and the user is bounced to the login
# screen at random. On single-process Render this only meant "logged out
# on restart". Refuse to boot rather than ship that behaviour.
if [ -z "${MAEC_SECRET_KEY:-}" ] || \
   [ "${MAEC_SECRET_KEY}" = "generate-a-long-random-value" ]; then
    echo "FATAL: MAEC_SECRET_KEY is unset or still the placeholder value." >&2
    echo "       With WEB_CONCURRENCY > 1 this causes random logouts," >&2
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

echo "MAEC backend starting: ${WEB_CONCURRENCY} worker process(es) on port ${PORT}"

# uvicorn --workers, not gunicorn: gunicorn's default 30 s worker timeout
# would kill a worker mid-parse on a large drawing set. Processes, not
# threads — MuPDF holds the GIL, so threads measure ~1.0x while separate
# processes actually scale.
exec uvicorn backend.main:app \
    --host 0.0.0.0 \
    --port "${PORT}" \
    --workers "${WEB_CONCURRENCY}" \
    --timeout-keep-alive 75
