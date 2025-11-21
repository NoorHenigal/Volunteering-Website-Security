"""Strict typed configuration settings."""

from datetime import timedelta
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with strict typing."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
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

    @property
    def async_database_url(self) -> str:
        """Generate async database URL."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def access_token_expiry(self) -> timedelta:
        """Get access token expiry as timedelta."""
        return timedelta(minutes=self.access_token_expire_minutes)

    @property
    def refresh_token_expiry(self) -> timedelta:
        """Get refresh token expiry as timedelta."""
        return timedelta(days=self.refresh_token_expire_days)


settings: Settings = Settings()
