DOCKER_COMPOSE = docker compose
BACKEND = cd backend && source .venv/bin/activate &&
DC_DEV  = $(DOCKER_COMPOSE) -f docker-compose.dev.yml
DC_PROD = $(DOCKER_COMPOSE) -f docker-compose.prod.yml

# Dev : infra (ports décalés) + backend + workers + frontend (hot-reload)
dev:
	$(DC_DEV) up -d

dev-build:
	$(DC_DEV) build

dev-down:
	$(DC_DEV) down

# Prod : infra + backend + workers + nginx (port 80)
prod:
	$(DC_PROD) up -d --build

prod-down:
	$(DC_PROD) down

build:
	$(DC_DEV) build

logs:
	$(DC_DEV) logs -f

logs-prod:
	$(DC_PROD) logs -f

clean:
	$(DC_PROD) down --rmi all --volumes --remove-orphans

# Recrée le schéma Postgres et insère les utilisateurs de dev.
# À relancer après chaque `make dev-down --volumes` + `make dev`.
reset-db:
	$(BACKEND) alembic stamp base
	$(BACKEND) alembic upgrade head
	$(BACKEND) python -m scripts.seed_validators
