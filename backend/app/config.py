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
    # Réglable pour une seule raison : permettre aux tests d'isoler leur propre
    # collection, exactement comme `POSTGRES_DB` est forcé en `<base>_test`
    # (cf. `_force_test_collection` dans tests/conftest.py). Ce n'est pas un
    # paramètre d'exploitation — le changer en production rend invisible tout ce
    # qui y est déjà indexé, sans rien signaler.
    qdrant_collection: str = "ticketai"

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
    albert_reverif_model_name: str = ""  # vide → utilise albert_llm_model_name
    albert_tag_model_name: str = "mistralai/Ministral-3-8B-Instruct-2512"  # quota séparé du modèle de génération

    # SEUILS
    seuil_canonique: int
    seuil_cosinus: float

    # Porte lexicale de l'étage de rappel. Un candidat atteint le juge si son
    # cosinus franchit le seuil **ou** si son score BM25 par terme franchit
    # celui-ci : on ne seuille pas la fusion, on seuille chaque signal sur sa
    # propre échelle. **`0` ferme la porte lexicale** et restitue exactement le
    # comportement d'avant BM25 — le filet en cas de calibration ratée.
    #
    # Par terme et non brut : un score BM25 est une somme sur les termes de la
    # requête, donc une question longue score mécaniquement plus haut. Mesuré le
    # 11/09/2026 : bruts 2,17 / 3,42 / 4,41, ramenés au terme 1,08 / 1,14 / 1,47.
    #
    # ⚠️ **À recalibrer quand le corpus grossit** : l'IDF que Qdrant applique croît
    # en log(N), donc l'échelle entière se déplace. La valeur ci-dessous est
    # mesurée sur 24 points et ne vaut que pour cet ordre de grandeur.
    seuil_lexical_par_terme: float = 1.0

    # FAQ — consultation des réponses canoniques par les utilisateurs.
    # `faq_seuil_pertinence` vaut par défaut SEUIL_SUGGESTION (seuil_cosinus − 0,05,
    # cf. services/question_pipeline.py:25) : le niveau à partir duquel le système
    # juge déjà qu'une réponse vaut la peine d'être proposée à un humain.
    # `faq_rate_limit_par_minute` protège le quota Albert (1 000 requêtes/jour/modèle) :
    # une recherche = un embedding. 0 désactive la limite.
    faq_max_resultats: int = 5
    faq_seuil_pertinence: float = 0.75
    faq_rate_limit_par_minute: int = 20
    faq_rate_limit_par_jour: int = 100

    # Quota tickets : protège la queue Celery et le quota Albert contre les abus.
    # 0 désactive la limite.
    ticket_rate_limit_par_jour: int = 50

    # Replay des tickets ÉCHOUÉ : âge maximal des tickets à remettre en queue.
    # Au-delà, on ne rejoue pas sans que l'utilisateur l'ait demandé.
    replay_max_age_jours: int = 7
    # Second rang, proposé explicitement comme incertain quand rien ne franchit
    # `faq_seuil_pertinence`. Mesuré : la bande sous le seuil mélange bonnes et
    # mauvaises correspondances (« hauteur fruit » → 0,67 juste, une demande
    # étrangère → 0,71 fausse), et aucun seuil ne les sépare. On ne peut donc pas
    # l'annoncer comme une réponse — seulement comme une piste.
    faq_seuil_incertain: float = 0.55

    # Verrou de ticket (durée du bail en secondes, prolongé par heartbeat)
    lock_ttl_seconds: int = 300

    # Fermeture automatique : délai en jours après validation avant auto-clôture
    jours_auto_cloture: int = 7

    # Documents storage
    documents_storage_path: str

    # CORS — origines autorisées (liste JSON dans .env, ex. ["https://app.example.fr"])
    allowed_origins: list[str] = ["http://localhost:5173", "http://localhost:4173"]

    # ── Authentification ─────────────────────────────────────────────
    jwt_secret_key: str
    jwt_algorithm: str
    access_token_expire_minutes: int

    # LDAP / Active Directory
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
