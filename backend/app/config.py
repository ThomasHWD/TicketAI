from functools import cached_property

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # PostgreSQL
    postgres_host: str
    postgres_port: int = 5432
    postgres_db: str
    postgres_user: str
    postgres_password: str

    # Qdrant
    qdrant_host: str
    qdrant_port: int = 6333
    qdrant_grpc_port: int = 6334

    # Valkey
    valkey_host: str
    valkey_port: int = 6379

    # IA
    llm_url: str
    llm_model_name: str
    albert_api_key: str
    albert_llm_url: str
    albert_llm_model_name: str
    albert_embeddings_url: str
    albert_embeddings_model_name: str
    albert_reranker_url: str
    albert_reranker_model_name: str

    # SEUILS
    seuil_canonique: int = 3
    seuil_cosinus: float = 0.70

    # Verrou de ticket (durée du bail en secondes, prolongé par heartbeat)
    lock_ttl_seconds: int = 300

    # Documents storage
    documents_storage_path: str

    # ── Authentification ─────────────────────────────────────────────
    # auth_mode == "mock"  → annuaire LDAP simulé en mémoire (dev, aucune conf requise)
    # auth_mode == "ldap"  → vrai serveur LDAP / Active Directory (conf ci-dessous)
    auth_mode: str = "mock"
    jwt_secret_key: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 480

    # LDAP / Active Directory (utilisés uniquement quand auth_mode == "ldap")
    ldap_server_url: str = "ldap://localhost:389"
    ldap_bind_dn: str = ""            # compte de service pour la recherche
    ldap_bind_password: str = ""
    ldap_user_search_base: str = "ou=users,dc=ticketai,dc=local"
    ldap_user_search_filter: str = "(sAMAccountName={username})"
    ldap_attr_email: str = "mail"
    ldap_attr_firstname: str = "givenName"
    ldap_attr_lastname: str = "sn"

    @cached_property
    def database_url(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @cached_property
    def valkey_url(self) -> str:
        return f"redis://{self.valkey_host}:{self.valkey_port}/0"

    model_config = {
        "env_file": ".env",
        "extra": "ignore"    # ← ignore les variables du .env non déclarées
    }

settings = Settings()
