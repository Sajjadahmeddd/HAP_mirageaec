# MAEC frontend — Vite build, served by nginx (which also fronts the API)
#   ->  frontend/Dockerfile
# Build context is ./frontend
#
# v2: also copies security-headers.conf into /etc/nginx/snippets/.
#     It must NOT go in conf.d/, which nginx auto-includes at http level —
#     that would apply the headers globally and duplicate them on /api/.

# ---- stage 1: build the bundle ---------------------------------------
FROM node:20-alpine AS build
WORKDIR /src

# Cached until the lockfile changes
COPY package*.json ./
RUN npm ci

COPY . .
# Produces /src/dist. No VITE_API_URL is needed or wanted: the app calls
# fetch('/api/...') on a relative path and nginx routes it to the backend,
# so the bundle is identical in every environment.
RUN npm run build

# ---- stage 2: serve --------------------------------------------------
FROM nginx:1.27-alpine AS runtime

# Our config replaces the default site
RUN rm -f /etc/nginx/conf.d/default.conf && mkdir -p /etc/nginx/snippets

COPY nginx.conf            /etc/nginx/conf.d/maec.conf
COPY security-headers.conf /etc/nginx/snippets/security-headers.conf
COPY --from=build /src/dist /usr/share/nginx/html

# Fail the BUILD on a malformed config, rather than discovering it when
# the container will not start.
# nginx resolves `upstream` server names when it PARSES the config, and the
# service name "backend" has no DNS during a build -- so a bare `nginx -t`
# fails with "host not found in upstream" on a config that is in fact
# correct. (Patching /etc/hosts does not help: BuildKit mounts it read-only.)
# So the check runs against a copy with the upstream pointed at loopback.
# Everything else is the real thing -- same maec.conf, and the snippet
# include is absolute so it still pulls the real security-headers.conf.
# A syntax error anywhere still fails the build, which is the point.
RUN mkdir -p /tmp/ngt/conf.d \
 && sed 's#server backend:8000;#server 127.0.0.1:8000;#' \
        /etc/nginx/conf.d/maec.conf > /tmp/ngt/conf.d/maec.conf \
 && sed 's#/etc/nginx/conf.d/#/tmp/ngt/conf.d/#' \
        /etc/nginx/nginx.conf > /tmp/ngt/nginx.conf \
 && nginx -t -p /tmp/ngt -c /tmp/ngt/nginx.conf \
 && rm -rf /tmp/ngt

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://127.0.0.1/healthz >/dev/null 2>&1 || exit 1

CMD ["nginx", "-g", "daemon off;"]
