"""Application configuration."""

import logging
from datetime import timedelta
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        strict=True,
        extra="forbid",
    )

    # Database settings
    postgres_user: str = Field(default=..., alias="POSTGRES_USER")
    postgres_password: str = Field(default=..., alias="POSTGRES_PASSWORD")
    postgres_db: str = Field(default=..., alias="POSTGRES_DB")
    postgres_host: str = Field(default=..., alias="POSTGRES_HOST")
    postgres_port: int = Field(default=..., alias="POSTGRES_PORT")

    # JWT settings
    secret_key: SecretStr = Field(default=..., alias="SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=15, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_days: int = Field(default=30, alias="REFRESH_TOKEN_EXPIRE_DAYS")

    # Cookie settings
    cookie_name: str = Field(default="refresh_token", alias="COOKIE_NAME")
    cookie_secure: bool = Field(default=False, alias="COOKIE_SECURE")
    cookie_httponly: bool = Field(default=True, alias="COOKIE_HTTPONLY")
    cookie_samesite: Literal["lax", "strict", "none"] = Field(default="lax", alias="COOKIE_SAMESITE")
    cookie_domain: str | None = Field(default=None, alias="COOKIE_DOMAIN")

    # Environment
    environment: str = Field(default="development", alias="ENVIRONMENT")

    # Database echo (SQL logging)
    database_echo: bool = Field(default=False, alias="DATABASE_ECHO")

    # Logging
    log_level: str = Field(default="normal", alias="LOG_LEVEL")

    # Demo Data
    demo_data: bool = Field(default=False, alias="DEMO_DATA")

    # Uploads (optional override)
    upload_dir: Path | None = Field(default=None, alias="UPLOAD_DIR")

    @property
    def database_url(self) -> str:
        """PostgreSQL connection URL."""
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def access_token_expiry(self) -> timedelta:
        """Access token expiry as timedelta."""
        return timedelta(minutes=self.access_token_expire_minutes)

    @property
    def refresh_token_expiry(self) -> timedelta:
        """Refresh token expiry as timedelta."""
        return timedelta(days=self.refresh_token_expire_days)


def _create_settings() -> Settings:
    try:
        return Settings()
    except Exception as e:
        if not Path(".env").exists():
            msg = "\n❌ Configuration missing!\n--> See README.md for setup instructions"
            raise RuntimeError(msg) from e
        raise


settings: Settings = _create_settings()


def _configure_logging() -> logging.Logger:
    level = logging.DEBUG if settings.log_level == "debug" else logging.WARNING
    logging.basicConfig(level=level, format="[%(levelname)s] %(message)s", force=True)
    return logging.getLogger("app")


log: logging.Logger = _configure_logging()
