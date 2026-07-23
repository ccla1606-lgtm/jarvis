"""Liveness and dependency readiness checks."""

from dataclasses import dataclass
from typing import Protocol

import psycopg


@dataclass(frozen=True, slots=True)
class ReadinessResult:
    """Normalized readiness result."""

    ready: bool
    detail: str


class ReadinessProbe(Protocol):
    """Port used by the API to check required dependencies."""

    def check(self) -> ReadinessResult:
        """Return dependency readiness without raising infrastructure errors."""


@dataclass(frozen=True, slots=True)
class PostgresReadinessProbe:
    """Readiness adapter backed by a real PostgreSQL connection."""

    database_url: str
    connect_timeout_seconds: int = 2

    def check(self) -> ReadinessResult:
        try:
            with psycopg.connect(
                self.database_url,
                connect_timeout=self.connect_timeout_seconds,
            ) as connection:
                value = connection.execute("SELECT 1").fetchone()
        except psycopg.Error as exc:
            return ReadinessResult(
                ready=False,
                detail=f"postgres unavailable: {exc.__class__.__name__}",
            )

        if value != (1,):
            return ReadinessResult(ready=False, detail="postgres readiness query failed")
        return ReadinessResult(ready=True, detail="postgres ready")
