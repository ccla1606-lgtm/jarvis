"""Small, deterministic PostgreSQL migration runner."""

import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from jarvis.config import get_settings

DEFAULT_MIGRATION_DIRECTORY = Path(__file__).with_name("sql")
_SCHEMA_PATTERN = re.compile(r"^[a-z_][a-z0-9_]*$")


class MigrationError(RuntimeError):
    """Base migration failure."""


class MigrationChecksumMismatchError(MigrationError):
    """An applied immutable migration was edited."""


@dataclass(frozen=True, slots=True)
class MigrationResult:
    applied: tuple[str, ...]
    current_version: str | None


def validate_schema_name(schema: str) -> str:
    if not _SCHEMA_PATTERN.fullmatch(schema):
        raise ValueError("database schema must match ^[a-z_][a-z0-9_]*$")
    return schema


def apply_migrations(
    database_url: str,
    *,
    schema: str = "public",
    migration_directory: Path = DEFAULT_MIGRATION_DIRECTORY,
) -> MigrationResult:
    """Apply every pending SQL file exactly once under an advisory lock."""

    validated_schema = validate_schema_name(schema)
    migration_paths = tuple(sorted(migration_directory.glob("*.sql")))
    if not migration_paths:
        raise MigrationError(f"no migrations found in {migration_directory}")

    applied: list[str] = []
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        connection.execute(
            sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(validated_schema))
        )
        connection.execute(
            sql.SQL("SET search_path TO {}").format(sql.Identifier(validated_schema))
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                checksum CHAR(64) NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtext(%s))",
            (f"jarvis:migrations:{validated_schema}",),
        )

        for migration_path in migration_paths:
            version = migration_path.name
            contents = migration_path.read_text(encoding="utf-8")
            checksum = sha256(contents.encode()).hexdigest()
            row = connection.execute(
                "SELECT checksum FROM schema_migrations WHERE version = %s",
                (version,),
            ).fetchone()
            if row is not None:
                if row["checksum"] != checksum:
                    raise MigrationChecksumMismatchError(
                        f"applied migration {version} checksum does not match"
                    )
                continue

            connection.execute(contents)
            connection.execute(
                "INSERT INTO schema_migrations (version, checksum) VALUES (%s, %s)",
                (version, checksum),
            )
            applied.append(version)

        current_row = connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1"
        ).fetchone()

    return MigrationResult(
        applied=tuple(applied),
        current_version=current_row["version"] if current_row is not None else None,
    )


def main() -> None:
    settings = get_settings()
    result = apply_migrations(
        settings.database_url,
        schema=settings.database_schema,
    )
    print(
        f"Jarvis database schema is at {result.current_version}; "
        f"applied {len(result.applied)} migration(s)"
    )


if __name__ == "__main__":
    main()
