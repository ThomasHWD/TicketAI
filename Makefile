DOCKER_COMPOSE = docker compose
BACKEND = cd backend && source .venv/bin/activate &&

build:
	$(DOCKER_COMPOSE) build

up:
	$(DOCKER_COMPOSE) up -d

down:
	$(DOCKER_COMPOSE) down

logs:
	$(DOCKER_COMPOSE) logs -f

clean:
	$(DOCKER_COMPOSE) down --rmi all --volumes --remove-orphans

# Recrée le schéma Postgres et insère les utilisateurs de dev.
# À relancer après chaque `make clean` + `make up`.
reset-db:
	$(BACKEND) alembic stamp base
	$(BACKEND) alembic upgrade head
	$(BACKEND) python -m scripts.seed_validators