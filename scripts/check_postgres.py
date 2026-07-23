"""Wait for the configured PostgreSQL test database."""

import os
import sys
import time

from jarvis.health import PostgresReadinessProbe


def main() -> int:
    database_url = os.environ.get("JARVIS_TEST_DATABASE_URL")
    if not database_url:
        print("JARVIS_TEST_DATABASE_URL is required", file=sys.stderr)
        return 2

    probe = PostgresReadinessProbe(database_url, connect_timeout_seconds=1)
    for _ in range(30):
        result = probe.check()
        if result.ready:
            print(result.detail)
            return 0
        time.sleep(1)

    print(result.detail, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

