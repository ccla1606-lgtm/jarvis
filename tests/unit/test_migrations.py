from pathlib import Path

import pytest

from jarvis.infrastructure.migrations import (
    DEFAULT_MIGRATION_DIRECTORY,
    MigrationError,
    apply_migrations,
    validate_schema_name,
)


@pytest.mark.parametrize("schema", ["public", "jarvis_test_123", "_private"])
def test_schema_name_accepts_safe_identifiers(schema: str) -> None:
    assert validate_schema_name(schema) == schema


@pytest.mark.parametrize("schema", ["", "Public", "bad-name", "bad.name", "1bad"])
def test_schema_name_rejects_unsafe_identifiers(schema: str) -> None:
    with pytest.raises(ValueError, match="schema"):
        validate_schema_name(schema)


def test_migration_runner_rejects_empty_directory(tmp_path: Path) -> None:
    with pytest.raises(MigrationError, match="no migrations"):
        apply_migrations(
            "postgresql://unused",
            migration_directory=tmp_path,
        )


def test_packaged_migrations_are_available() -> None:
    assert (DEFAULT_MIGRATION_DIRECTORY / "0001_domain.sql").is_file()
    assert (DEFAULT_MIGRATION_DIRECTORY / "0002_command_idempotency.sql").is_file()
