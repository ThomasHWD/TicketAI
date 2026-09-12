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

# ⚠️ `clean` vise la PROD, pas le dev. Les deux fichiers Compose déclarent des
# projets séparés (`ticketai` vs `ticketai-dev`), donc des volumes disjoints :
# lancé ici, `down --rmi all --volumes` détruit les données de PRODUCTION
# (Postgres, Qdrant, documents) et toutes les images — en laissant le dev intact,
# c'est-à-dire l'inverse exact de ce que le nom laisse croire.
# Deux garde-fous, puisque le nom ne prévient de rien :
#   1. refus si des conteneurs de prod tournent ;
#   2. sinon, confirmation explicite par CONFIRM=1.
# Pour remettre le DEV à zéro, c'est `make dev-clean`.
clean:
	@test -z "$$($(DC_PROD) ps -q)" \
		|| { echo "clean : des conteneurs de PROD tournent. Ce target détruit les volumes de PRODUCTION (Postgres, Qdrant, documents). Arrêtez la prod d'abord si c'est réellement l'intention — sinon vous cherchez 'make dev-clean'."; exit 1; }
	@test "$(CONFIRM)" = "1" \
		|| { echo "clean : détruit les VOLUMES DE PROD et toutes les images. Relancez avec 'make clean CONFIRM=1' si c'est voulu. Pour repartir de zéro en dev : 'make dev-clean'."; exit 1; }
	$(DC_PROD) down --rmi all --volumes --remove-orphans

# Remise à zéro du DEV : conteneurs + volumes du projet ticketai-dev uniquement.
# C'est ce que `make clean` a l'air de faire et ne fait pas.
# Enchaîner avec `make dev && make reset-db` pour repartir sur une base saine.
dev-clean:
	$(DC_DEV) down --volumes --remove-orphans
	@echo "Dev remis à zéro. Enchaînez : make dev && make reset-db"

# Recrée le schéma Postgres de DEV et insère les utilisateurs de dev.
# À relancer après `docker compose -f docker-compose.dev.yml down --volumes` + `make dev`.
# Prérequis : la stack de dev tourne (`make dev`). Voir Docs/onboarding-dev.md § 10.
reset-db:
	@$(DC_DEV) ps --status running --services | grep -qx backend \
		|| { echo "reset-db : le conteneur backend de dev ne tourne pas — lancez 'make dev'."; exit 1; }
	$(DEV_EXEC) alembic stamp base
	$(DEV_EXEC) alembic upgrade head
	$(DEV_EXEC) python -m scripts.seed_validators
