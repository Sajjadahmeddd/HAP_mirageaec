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
RUN nginx -t

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://127.0.0.1/healthz >/dev/null 2>&1 || exit 1

CMD ["nginx", "-g", "daemon off;"]
