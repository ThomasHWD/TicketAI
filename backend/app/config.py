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
