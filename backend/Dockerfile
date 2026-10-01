# syntax=docker/dockerfile:1
FROM python:3.14-slim

# TRANSFORMERS_NO_ADVISORY_WARNINGS : « PyTorch was not found » à chaque démarrage de process — seul le tokenizer sert.
ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TRANSFORMERS_NO_ADVISORY_WARNINGS=1

WORKDIR /app

# curl : healthcheck (5 ms vs 111 ms CPython) ; wheels manylinux disponibles pour toutes les dépendances — gcc inutile.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Cache BuildKit : réinstalle sans retélécharger ; --no-cache-dir retiré car il interdisait cette réutilisation.
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# UID/GID alignés sur l'hôte pour le bind-mount dev ; déclarés ici (pas en tête) — un ARG invalide tout le cache qui le suit.
ARG UID=1001
ARG GID=1001

# /var/lib/celery hors de /app : le schedule beat n'atterrit pas dans le dépôt bind-monté en root ; chown -R ici = répertoires vides seulement.
RUN groupadd -g "$GID" app \
    && useradd -u "$UID" -g "$GID" -m -s /bin/sh app \
    && mkdir -p /app/storage /app/uploads_tmp /var/lib/celery \
    && chown -R app:app /app /var/lib/celery
USER app

# Tokenizer embarqué : affranchit du réseau HF et fige la version (diff de réindexation reproductibles) ; ⚠️ avant le COPY — après, chaque .py invalide cette couche.
RUN python -c "from transformers import AutoTokenizer; AutoTokenizer.from_pretrained('BAAI/bge-m3')"

# Dernière couche : tout changement de code l'invalide ; .dockerignore filtre .venv (6,1 Go) ; --chown évite un chown -R en couche séparée.
COPY --chown=app:app . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
