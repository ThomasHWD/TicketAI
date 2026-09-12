# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# curl sert au healthcheck Docker (cf. docker-compose.{dev,prod}.yml) : lancer
# un interpréteur CPython complet toutes les 5 s coûte ~111 ms contre ~5 ms ici.
#
# Plus de gcc ni libpq-dev : ils ne servaient qu'à compiler des sources, or
# toutes les dépendances restantes ont une wheel manylinux pour cp312 (psycopg2
# est tiré en `-binary`). 206 Mo et un `apt-get update` en moins. Si un futur
# paquet n'a pas de wheel, le build échouera ici, franchement — les remettre à
# ce moment-là, pas « au cas où ».
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Cache BuildKit sur le répertoire pip : un changement de requirements.txt
# réinstalle sans retélécharger les wheels inchangées. Le cache vit dans le
# builder, pas dans une couche de l'image — d'où l'abandon de --no-cache-dir,
# qui n'économisait plus rien et interdisait justement cette réutilisation.
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# UID/GID alignés sur ceux de l'hôte. En dev, `./backend` est bind-monté sur
# /app : si l'utilisateur du conteneur n'a pas le même UID que le propriétaire
# des fichiers, Python ne peut plus écrire ses __pycache__ et tout fichier créé
# depuis le conteneur atterrit dans le dépôt avec un propriétaire inattendu.
# 1001 = l'UID de la machine de dev actuelle. Sur un hôte différent :
#   docker compose build --build-arg UID=$(id -u) --build-arg GID=$(id -g)
#
# Déclarés ICI et pas en tête de fichier : un ARG invalide le cache de tout ce
# qui le suit, donc en haut le moindre changement d'UID relançait le pip install.
ARG UID=1001
ARG GID=1001

# Utilisateur non privilégié. /var/lib/celery reçoit le schedule de beat, qui
# atterrissait sinon dans le WORKDIR — donc, en dev, dans le dépôt bind-monté,
# en root. Le sortir de /app permet de ne plus exiger que le code soit
# inscriptible, et supprime au passage un fichier root-owned dans l'arbre git.
#
# Le `chown -R` ne voit ici que des répertoires vides : le code arrive après,
# déjà au bon propriétaire via `COPY --chown`. Quand il précédait cette couche,
# il repassait sur tout l'arbre à chaque changement de code — 5,2 s pour rien.
RUN groupadd -g "$GID" app \
    && useradd -u "$UID" -g "$GID" -m -s /bin/sh app \
    && mkdir -p /app/storage /app/uploads_tmp /var/lib/celery \
    && chown -R app:app /app /var/lib/celery
USER app

# Tokenizer BGE-M3 embarqué à la construction. Sans ça `get_splitter()` le tire
# de huggingface.co au premier découpage : l'ingestion dépendait donc du réseau
# vers HF et de ses quotas anonymes, et le cache vivant dans le home du
# conteneur (sans volume), les 22 Mo repartaient à chaque recréation.
# Effet de bord souhaitable : la version du tokenizer est figée dans l'image au
# lieu de suivre ce que HF sert ce jour-là — le découpage devient reproductible,
# ce qui est ce dont dépendent les diff de réindexation.
#
# ⚠️ AVANT le COPY du code, et c'est tout l'intérêt. Placée après, cette couche
# était invalidée par le moindre changement de `.py` : 11,4 s mesurées et un
# aller-retour vers huggingface.co à CHAQUE build. Embarquer le tokenizer pour
# affranchir l'exécution du réseau HF, tout en y réexposant le build, n'avait
# aucun sens. Ne rien insérer entre cette ligne et le COPY ci-dessous.
RUN python -c "from transformers import AutoTokenizer; AutoTokenizer.from_pretrained('BAAI/bge-m3')"

# En dernier : c'est la couche que le moindre changement de code invalide, donc
# rien de coûteux ne doit la suivre. Ce qu'elle embarque est filtré par
# .dockerignore (sans lui, `backend/.venv` y versait 6,1 Go et
# `celerybeat-schedule` cassait le cache à chaque build).
# `--chown` : l'ownership est posé pendant la copie, ce qui évite un `chown -R`
# en couche séparée — lequel dupliquerait en plus tout l'arbre copié.
COPY --chown=app:app . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
