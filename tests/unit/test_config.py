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
