import pytest
from pydantic import ValidationError

from jarvis.config import Settings


def test_settings_accept_explicit_test_configuration() -> None:
    settings = Settings(
        environment="test",
        service_name="jarvis-test",
        database_url="postgresql://example/test",
        database_schema="jarvis_test",
        database_connect_timeout_seconds=3,
    )

    assert settings.environment == "test"
    assert settings.service_name == "jarvis-test"
    assert settings.database_schema == "jarvis_test"
    assert settings.database_connect_timeout_seconds == 3


def test_production_rejects_default_development_api_token() -> None:
    with pytest.raises(ValidationError, match="non-default JARVIS_API_TOKEN"):
        Settings(
            environment="production",
            database_url="postgresql://example/production",
        )


def test_production_accepts_explicit_api_token() -> None:
    settings = Settings(
        environment="production",
        database_url="postgresql://example/production",
        api_token="production-secret",
    )

    assert settings.api_token.get_secret_value() == "production-secret"
