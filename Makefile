DOCKER_COMPOSE = docker compose
BACKEND = cd backend && source .venv/bin/activate &&
DC_INFRA = $(DOCKER_COMPOSE) -f docker-compose.yml
DC_DEV   = $(DOCKER_COMPOSE) -f docker-compose.yml -f docker-compose.dev.yml
DC_PROD  = $(DOCKER_COMPOSE) -f docker-compose.yml -f docker-compose.prod.yml

# Infra seule (postgres, qdrant, valkey)
up:
	$(DC_INFRA) up -d

down:
	$(DC_INFRA) down

# Dev : infra + backend + workers + frontend (hot-reload)
dev:
	$(DC_DEV) up

dev-build:
	$(DC_DEV) build

dev-down:
	$(DC_DEV) down

# Prod : tout en mode optimisé + nginx
prod:
	$(DC_PROD) up -d --build

prod-down:
	$(DC_PROD) down

build:
	$(DC_DEV) build

logs:
	$(DC_DEV) logs -f

clean:
	$(DC_PROD) down --rmi all --volumes --remove-orphans

# Recrée le schéma Postgres et insère les utilisateurs de dev.
# À relancer après chaque `make clean` + `make up`.
reset-db:
	$(BACKEND) alembic stamp base
	$(BACKEND) alembic upgrade head
	$(BACKEND) python -m scripts.seed_validators