import os
from collections.abc import Iterator
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from jarvis.infrastructure.migrations import apply_migrations
from jarvis.infrastructure.postgres_repository import PostgresTaskRepository


@pytest.fixture
def database_url() -> str:
    value = os.environ.get("JARVIS_TEST_DATABASE_URL")
    if not value:
        pytest.fail(
            "JARVIS_TEST_DATABASE_URL is required for integration tests; "
            "run make bootstrap or use the CI PostgreSQL service"
        )
    return value


@pytest.fixture
def postgres_schema(database_url: str) -> Iterator[str]:
    schema = f"jarvis_test_{uuid4().hex}"
    with psycopg.connect(database_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    try:
        yield schema
    finally:
        with psycopg.connect(database_url, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


@pytest.fixture
def postgres_repository(
    database_url: str,
    postgres_schema: str,
) -> PostgresTaskRepository:
    apply_migrations(database_url, schema=postgres_schema)
    return PostgresTaskRepository(database_url, schema=postgres_schema)
