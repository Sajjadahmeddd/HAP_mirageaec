# MAEC backend — FastAPI + PyMuPDF engine
# Build context is the REPO ROOT (see docker-compose.yml).
#
# v2 changes after Gate 0:
#   - removed `COPY airsizer/` — it lives at hap_converter/airsizer/ and is
#     already covered by the hap_converter copy below (B1)
#   - startup guards moved into docker-entrypoint.sh (B3), which is far
#     easier to read and test than an escaped JSON-array CMD

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# ---- dependencies -----------------------------------------------------
# Alone first, so this layer caches until requirements.txt changes.
# PyMuPDF ships manylinux wheels — no compiler needed.
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# ---- application ------------------------------------------------------
# hap_converter/ contains airsizer/ as a subpackage — do NOT add a
# separate COPY for it (that was the Gate 0 build-breaking bug).
COPY backend/         ./backend/
COPY hap_converter/   ./hap_converter/
COPY config/          ./config/

# Normalise line endings in case the file was checked out on Windows with
# core.autocrlf=true — a CRLF shebang fails with an opaque "not found".
COPY backend/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/docker-entrypoint.sh \
 && chmod +x /usr/local/bin/docker-entrypoint.sh

RUN useradd --create-home --uid 10001 maec \
 && mkdir -p /tmp/maec-uploads \
 && chown -R maec:maec /app /tmp/maec-uploads
USER maec

ENV TMPDIR=/tmp/maec-uploads \
    PORT=8000 \
    WEB_CONCURRENCY=6

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=4).status==200 else 1)"

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
