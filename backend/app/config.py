from functools import cached_property

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    postgres_host: str
    postgres_port: int
    postgres_db: str
    postgres_user: str
    postgres_password: str

    qdrant_host: str
    qdrant_port: int
    qdrant_grpc_port: int
    # Adjustable only so tests can isolate their own collection. Changing it in production silently hides everything
    qdrant_collection: str = "ticketai"

    valkey_host: str
    valkey_port: int

    albert_api_key: str
    albert_llm_url: str
    albert_llm_model_name: str
    albert_embeddings_url: str
    albert_embeddings_model_name: str
    albert_reranker_url: str
    albert_reranker_model_name: str
    albert_garde_model_name: str = ""  # vide → utilise albert_llm_model_name
    albert_reverif_model_name: str = ""  # vide → utilise albert_llm_model_name
    albert_tag_model_name: str = "mistralai/Ministral-3-8B-Instruct-2512"  # quota séparé du modèle de génération
    albert_contexte_model_name: str = ""  # vide → utilise albert_tag_model_name

    # Kill-switch: `false` restores pre-contextualization behavior with zero extra Albert calls and no re-indexing.
    contextualisation_active: bool = True

    seuil_canonique: int
    seuil_cosinus: float

    # Lexical recall gate: per-term BM25. 0 closes it. ⚠️ Recalibrate as corpus grows: Qdrant IDF scales with log(N).
    seuil_lexical_par_terme: float = 1.0

    faq_max_resultats: int = 5
    faq_seuil_pertinence: float = 0.75
    faq_rate_limit_par_minute: int = 20  # one search = one Albert embedding; 0 disables
    faq_rate_limit_par_jour: int = 100
    ticket_rate_limit_par_jour: int = 50  # 0 disables
    replay_max_age_jours: int = 7
    # second tier shown only when no confident result — sub-threshold band mixes true and false positives with no
    faq_seuil_incertain: float = 0.55

    log_level: str = "INFO"  # DEBUG shows each retrieval step of a question (scores, rerank)

    lock_ttl_seconds: int = 300  # bail prolongé par heartbeat
    jours_auto_cloture: int = 7
    documents_storage_path: str
    allowed_origins: list[str] = ["http://localhost:5173", "http://localhost:4173"]  # liste JSON dans .env

    jwt_secret_key: str
    jwt_algorithm: str
    access_token_expire_minutes: int

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
            raise ValueError("JWT_SECRET_KEY doit faire au moins 32 caractères (générer avec : openssl rand -hex 32)")
        return self

    @model_validator(mode="after")
    def _validate_groupes_ldap(self) -> "Settings":
        # Fail at boot, not at login: an unset group silently strips its role from everyone (it used to grant ADMIN).
        if self.ldap_server_url:
            for nom in ("ldap_group_admin", "ldap_group_gestionnaire"):
                if not getattr(self, nom).strip():
                    raise ValueError(f"{nom.upper()} requis quand LDAP_SERVER_URL est renseigné (nom ou DN du groupe)")
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
        "extra": "ignore",
    }


settings = Settings()
