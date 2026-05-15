"""Configuracoes via pydantic-settings, lendo de secrets/.env."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent.parent.parent.parent / "secrets/.env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    ENVIRONMENT: Literal["local", "dev", "staging", "production"] = "local"

    # Postgres
    POSTGRES_USER: str
    POSTGRES_PASSWORD: SecretStr
    POSTGRES_DB: str
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    # RabbitMQ
    RABBITMQ_USER: str
    RABBITMQ_PASSWORD: SecretStr
    RABBITMQ_HOST: str = "localhost"
    RABBITMQ_PORT: int = 5672

    # Qdrant
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333

    # APIs externas (sistema-level)
    ANTHROPIC_API_KEY: SecretStr
    VOYAGE_API_KEY: SecretStr

    # Dreaming (research preview Anthropic — Bloco H).
    # False = jobs registrados como CANDIDATE pra visibilidade, sem chamada API.
    # True = tenta consolidar via SDK; se SDK não expoe beta.dreams, marca como
    # SKIPPED_UNAVAILABLE (a menos que DREAMING_ALLOW_RAW_HTTP=True).
    DREAMING_ENABLED: bool = False
    DREAMING_ALLOW_RAW_HTTP: bool = False
    DREAMING_MODEL: str = "claude-sonnet-4-6"

    # Onboarding Analyzer v2 (PR-3 do redesign).
    # Diretorio base onde o backend clona repos pra RAG ingest local. Cada
    # task fica isolada em {CLONE_BASE_DIR}/{client_id}/{task_id}/. Em prod
    # apontar pra volume Docker named ou /var/lib/dev-autonomo/clones.
    CLONE_BASE_DIR: str = "~/.local/share/dev-autonomo/clones"

    # Modelo Claude usado pelo grader independente que checa o outcome
    # rubric do OA scan v2. Haiku eh ~25x mais barato que Opus e adequado
    # pra checagem de rubric (nao precisa raciocinar profundo, so verificar).
    GRADER_MODEL: str = "claude-haiku-4-5-20251001"

    # Maximo de iteracoes do loop OA <-> grader. Quando esgota, task vai pra
    # FAILED com motivo. 3 e o equilibrio Anthropic recomenda — suficiente
    # pra OA corrigir lacunas obvias, sem permitir loop infinito por erro
    # estrutural do prompt.
    OA_GRADER_MAX_ITERATIONS: int = 3

    # Master key Fernet pra encryptar segredos no banco
    MASTER_ENCRYPTION_KEY: SecretStr | None = None

    # JWT / sessions do painel
    SECRET_KEY: SecretStr | None = None

    # Temporario - vai migrar para o banco quando o painel existir
    GITHUB_TOKEN: SecretStr | None = None
    JIRA_BASE_URL: str | None = None
    JIRA_EMAIL: str | None = None
    JIRA_API_TOKEN: SecretStr | None = None
    JIRA_PROJECT_KEY: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_async_url(self) -> str:
        pwd = self.POSTGRES_PASSWORD.get_secret_value()
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{pwd}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_sync_url(self) -> str:
        pwd = self.POSTGRES_PASSWORD.get_secret_value()
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{pwd}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def redis_url(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def rabbitmq_url(self) -> str:
        pwd = self.RABBITMQ_PASSWORD.get_secret_value()
        return (
            f"amqp://{self.RABBITMQ_USER}:{pwd}"
            f"@{self.RABBITMQ_HOST}:{self.RABBITMQ_PORT}/"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
