# MAEC frontend — Vite build, served by nginx (which also fronts the API)
# Build context is ./frontend

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
RUN rm -f /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/maec.conf
COPY --from=build /src/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://127.0.0.1/healthz >/dev/null 2>&1 || exit 1

CMD ["nginx", "-g", "daemon off;"]
