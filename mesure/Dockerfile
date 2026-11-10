# syntax=docker/dockerfile:1
# =============================================================================
# Millésime — image du test de mesure (multi-stage)
#   1. builder : installe les paquets Python dans un environnement virtuel
#   2. final   : Python slim + l'environnement, sans outils de compilation
#
# Le modèle genderage.onnx (InsightFace, usage non commercial) n'est PAS dans
# l'image : il est téléchargé au premier lancement dans /data/models.
# =============================================================================

FROM python:3.12-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /venv
COPY requirements.txt .
RUN /venv/bin/pip install -r requirements.txt

FROM python:3.12-slim
ARG VERSION=dev
LABEL org.opencontainers.image.source="https://github.com/baloodusudouest/Millesime" \
      org.opencontainers.image.description="Millésime — test de mesure : précision de l'estimation d'âge sur les scans Immich" \
      org.opencontainers.image.version="${VERSION}"
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/venv/bin:$PATH" \
    DATA_DIR=/data
COPY --from=builder /venv /venv
WORKDIR /app
COPY mesure.py /app/mesure.py
RUN mkdir -p /data
VOLUME ["/data"]
CMD ["python", "/app/mesure.py"]
