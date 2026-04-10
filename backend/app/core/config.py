from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Required vars must be set or the app refuses to start (no silent defaults).
    Per-tenant secrets live in MongoDB / AWS Secrets Manager — never as env vars.
    Source of truth: docs/standards/env.md
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # ── App ───────────────────────────────────────────────────────────────────
    APP_ENV: Literal["development", "staging", "production"] = Field(
        default="development",
        description="Deployment environment",
    )
    APP_DEBUG: bool = Field(default=False, description="Enable debug mode (never true in prod)")
    APP_HOST: str = Field(default="0.0.0.0", description="Server bind host")
    APP_PORT: int = Field(default=8000, ge=1, le=65535, description="Server bind port")
    APP_LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")
    APP_SECRET_KEY: SecretStr = Field(
        ...,
        min_length=32,
        description="JWT signing key — minimum 32 characters",
    )

    # ── MongoDB ───────────────────────────────────────────────────────────────
    MONGODB_URI: str = Field(..., description="MongoDB connection string")
    MONGODB_DATABASE: str = Field(..., min_length=1, description="MongoDB database name")

    # ── Neon (Postgres) ───────────────────────────────────────────────────────
    NEON_DATABASE_URL: str = Field(..., description="Pooled Postgres connection string")
    NEON_DIRECT_URL: str = Field(default="", description="Direct (non-pooled) URL, migrations")

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str = Field(..., description="Redis connection string")

    # ── RabbitMQ ──────────────────────────────────────────────────────────────
    RABBITMQ_URL: str = Field(..., description="RabbitMQ AMQP connection string")

    # ── AWS ───────────────────────────────────────────────────────────────────
    AWS_REGION: str = Field(default="us-east-1", description="AWS region")
    AWS_ACCESS_KEY_ID: SecretStr = Field(..., description="IAM access key")
    AWS_SECRET_ACCESS_KEY: SecretStr = Field(..., description="IAM secret key")
    AWS_S3_BUCKET: str = Field(..., min_length=1, description="S3 bucket for uploads")

    # ── Sentry ────────────────────────────────────────────────────────────────
    SENTRY_DSN: str = Field(default="", description="Sentry project DSN (empty disables)")
    SENTRY_ENVIRONMENT: str = Field(default="", description="Defaults to APP_ENV at runtime")
    SENTRY_TRACES_SAMPLE_RATE: float = Field(default=0.1, ge=0.0, le=1.0)

    # ── Flower (Celery dashboard) ─────────────────────────────────────────────
    FLOWER_PORT: int = Field(default=5555, ge=1, le=65535)
    FLOWER_BASIC_AUTH: str = Field(default="", description="user:password — required in prod")

    # ── Celery (derived from RabbitMQ + Redis) ────────────────────────────────
    # Uppercase to match Celery's own attribute/env-var convention.
    @property
    def CELERY_BROKER_URL(self) -> str:  # noqa: N802
        return self.RABBITMQ_URL

    @property
    def CELERY_RESULT_BACKEND(self) -> str:  # noqa: N802
        return self.REDIS_URL

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance.

    Lazy: instantiated on first call so tests/CI without full env can still
    import the module without triggering validation.
    """
    return Settings()
