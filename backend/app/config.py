from functools import cached_property

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # PostgreSQL
    postgres_host: str
    postgres_port: int
    postgres_db: str
    postgres_user: str
    postgres_password: str

    # Qdrant
    qdrant_host: str
    qdrant_port: int
    qdrant_grpc_port: int

    # Valkey
    valkey_host: str
    valkey_port: int

    # IA
    albert_api_key: str
    albert_llm_url: str
    albert_llm_model_name: str
    albert_embeddings_url: str
    albert_embeddings_model_name: str
    albert_reranker_url: str
    albert_reranker_model_name: str
    albert_garde_model_name: str = ""   # vide → utilise albert_llm_model_name
    albert_reverif_model_name: str = ""  # vide → utilise albert_llm_model_name
    albert_tag_model_name: str = "mistralai/Ministral-3-8B-Instruct-2512"  # quota séparé du modèle de génération

    # SEUILS
    seuil_canonique: int
    seuil_cosinus: float

    # Verrou de ticket (durée du bail en secondes, prolongé par heartbeat)
    lock_ttl_seconds: int = 300

    # Fermeture automatique : délai en jours après validation avant auto-clôture
    jours_auto_cloture: int = 7

    # Documents storage
    documents_storage_path: str

    # CORS — origines autorisées (liste JSON dans .env, ex. ["https://app.example.fr"])
    allowed_origins: list[str] = ["http://localhost:5173", "http://localhost:4173"]

    # ── Authentification ─────────────────────────────────────────────
    # auth_mode == "ldap" → interroge l'Active Directory.
    # Toute autre valeur → fallback base de données seule (tests, offline).
    auth_mode: str
    jwt_secret_key: str
    jwt_algorithm: str
    access_token_expire_minutes: int

    # LDAP / Active Directory (utilisés uniquement quand auth_mode == "ldap")
    ldap_server_url: str = ""
    ldap_bind_dn: str = ""
    ldap_bind_password: str = ""
    ldap_user_search_base: str = ""
    ldap_user_search_filter: str = ""
    ldap_attr_email: str = ""
    ldap_attr_firstname: str = ""
    ldap_attr_lastname: str = ""
    ldap_attr_department: str = ""
    ldap_group_gestionnaire: str = ""
    ldap_group_admin: str = ""
    ldap_server_url_secondary: str = ""
    ldap_tls_validate: bool = True
    ldap_timeout: int = 5

    @model_validator(mode="after")
    def _validate_jwt_secret(self) -> "Settings":
        if len(self.jwt_secret_key) < 32:
            raise ValueError(
                "JWT_SECRET_KEY doit faire au moins 32 caractères "
                "(générer avec : openssl rand -hex 32)"
            )
        return self

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
        "extra": "ignore",  # ← ignore les variables du .env non déclarées
    }


settings = Settings()
