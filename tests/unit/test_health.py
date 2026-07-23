from typing import Any

import psycopg

from jarvis.health import PostgresReadinessProbe


def test_postgres_probe_classifies_connection_error(monkeypatch: Any) -> None:
    def fail_connect(*args: object, **kwargs: object) -> None:
        raise psycopg.OperationalError("connection failed")

    monkeypatch.setattr(psycopg, "connect", fail_connect)
    probe = PostgresReadinessProbe("postgresql://unavailable", connect_timeout_seconds=1)

    result = probe.check()

    assert result.ready is False
    assert result.detail == "postgres unavailable: OperationalError"
