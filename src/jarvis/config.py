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
    model_mode: Literal["deterministic", "live"] = "deterministic"
    openai_api_key: SecretStr | None = None
    deepseek_api_key: SecretStr | None = None
    openai_fast_model: str = "gpt-5.6-luna"
    openai_reasoning_model: str = "gpt-5.6-terra"
    deepseek_fast_model: str = "deepseek-v4-flash"
    deepseek_reasoning_model: str = "deepseek-v4-pro"

    @model_validator(mode="after")
    def validate_runtime_mode(self) -> "Settings":
        if (
            self.environment == "production"
            and self.api_token.get_secret_value() == "development-only-token"
        ):
            raise ValueError("production requires a non-default JARVIS_API_TOKEN")
        if self.environment == "production" and self.model_mode != "live":
            raise ValueError("production requires JARVIS_MODEL_MODE=live")
        if self.model_mode == "live":
            missing = [
                name
                for name, value in (
                    ("JARVIS_OPENAI_API_KEY", self.openai_api_key),
                    ("JARVIS_DEEPSEEK_API_KEY", self.deepseek_api_key),
                )
                if value is None or not value.get_secret_value()
            ]
            if missing:
                raise ValueError(
                    "live model mode requires credentials: " + ", ".join(missing)
                )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return one validated settings instance per process."""

    return Settings()
