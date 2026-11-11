# syntax=docker/dockerfile:1
# =============================================================================
# Millésime — appli du NAS (multi-stage)
#   1. interface : Svelte 5 + Tailwind compilés
#   2. roues     : dépendances Python
#   3. final     : Python slim, sans Node ni outils de compilation, sans modèle
#                  (les calculs MiVOLO se font sur le PC, image « calcul »)
# =============================================================================

FROM node:22-bookworm-slim AS interface
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN mkdir -p /app && npx vite build --outDir /app/static --emptyOutDir

FROM python:3.12-slim-bookworm AS roues
WORKDIR /build
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

FROM python:3.12-slim-bookworm
ARG VERSION=dev
LABEL org.opencontainers.image.title="millesime" \
      org.opencontainers.image.description="Dater les scans de photos papier dans Immich (écran de comparaison + indice MiVOLO calculé sur le PC)" \
      org.opencontainers.image.source="https://github.com/baloodusudouest/Millesime" \
      org.opencontainers.image.version="${VERSION}"
RUN apt-get update && apt-get install -y --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/*
COPY --from=roues /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels
WORKDIR /srv
COPY app ./app
COPY --from=interface /app/static ./app/static
ENV TZ=Europe/Paris \
    MILLESIME_ETAT=/state \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
VOLUME ["/state"]
EXPOSE 8098
HEALTHCHECK --interval=60s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8098/health')" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8098", "--no-access-log"]
