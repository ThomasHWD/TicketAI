from functools import cached_property

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
    albert_garde_model_name: str = ""  # vide → utilise albert_llm_model_name

    # SEUILS
    seuil_canonique: int
    seuil_cosinus: float

    # Verrou de ticket (durée du bail en secondes, prolongé par heartbeat)
    lock_ttl_seconds: int = 300

    # Fermeture automatique : délai en jours après validation avant auto-clôture
    jours_auto_cloture: int = 7

    # Documents storage
    documents_storage_path: str

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
    ldap_tls_validate: bool = False
    ldap_timeout: int = 5

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
