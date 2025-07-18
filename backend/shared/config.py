"""Global configuration loaded from environment variables."""

from __future__ import annotations

from pydantic import AnyUrl, HttpUrl, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized configuration for backend services."""

    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="", secrets_dir="/run/secrets"
    )

    database_url: AnyUrl = AnyUrl("sqlite:///shared.db")
    kafka_bootstrap_servers: str = "localhost:9092"
    schema_registry_url: HttpUrl = HttpUrl("http://localhost:8081")
    redis_url: RedisDsn = RedisDsn("redis://localhost:6379/0")
    score_cache_ttl: int = 3600
    trending_ttl: int = 3600
    s3_endpoint: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_bucket: str | None = None
    secret_key: str | None = None
    allowed_origins: list[str] = ["*"]

    @field_validator("score_cache_ttl", "trending_ttl")
    @classmethod
    def _positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("must be positive")
        return value


Settings.model_rebuild()
settings: Settings = Settings()
