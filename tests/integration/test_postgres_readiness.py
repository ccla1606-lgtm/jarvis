import os

import pytest

from jarvis.health import PostgresReadinessProbe


@pytest.mark.integration
def test_real_postgres_is_ready() -> None:
    database_url = os.environ.get("JARVIS_TEST_DATABASE_URL")
    if not database_url:
        pytest.fail(
            "JARVIS_TEST_DATABASE_URL is required for integration tests; "
            "run make bootstrap or use the CI PostgreSQL service"
        )

    result = PostgresReadinessProbe(
        database_url=database_url,
        connect_timeout_seconds=3,
    ).check()

    assert result.ready is True, result.detail
