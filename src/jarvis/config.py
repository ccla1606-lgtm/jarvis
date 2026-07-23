"""Application configuration."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="JARVIS_",
        extra="ignore",
        case_sensitive=False,
    )

    environment: Literal["development", "test", "production"] = "development"
    service_name: str = "jarvis-api"
    database_url: str = Field(
        default="postgresql://jarvis:jarvis@localhost:5432/jarvis",
        min_length=1,
    )
    database_schema: str = Field(
        default="public",
        pattern=r"^[a-z_][a-z0-9_]*$",
    )
    database_connect_timeout_seconds: int = Field(default=2, ge=1, le=30)
    api_token: SecretStr = SecretStr("development-only-token")

    @model_validator(mode="after")
    def require_nondefault_production_token(self) -> "Settings":
        if (
            self.environment == "production"
            and self.api_token.get_secret_value() == "development-only-token"
        ):
            raise ValueError("production requires a non-default JARVIS_API_TOKEN")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return one validated settings instance per process."""

    return Settings()
