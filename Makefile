DOCKER_COMPOSE = docker compose
DC_DEV  = $(DOCKER_COMPOSE) -f docker-compose.dev.yml
DC_PROD = $(DOCKER_COMPOSE) -f docker-compose.prod.yml
# Exécute une commande DANS le conteneur backend de dev. Lancée depuis l'hôte,
# elle lirait backend/.env — qui pointe vers 5432/6333, c'est-à-dire la PROD.
DEV_EXEC = $(DC_DEV) exec -T backend

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

# Recrée le schéma Postgres de DEV et insère les utilisateurs de dev.
# À relancer après `docker compose -f docker-compose.dev.yml down --volumes` + `make dev`.
# Prérequis : la stack de dev tourne (`make dev`). Voir Docs/onboarding-dev.md § 10.
reset-db:
	@$(DC_DEV) ps --status running --services | grep -qx backend \
		|| { echo "reset-db : le conteneur backend de dev ne tourne pas — lancez 'make dev'."; exit 1; }
	$(DEV_EXEC) alembic stamp base
	$(DEV_EXEC) alembic upgrade head
	$(DEV_EXEC) python -m scripts.seed_validators
