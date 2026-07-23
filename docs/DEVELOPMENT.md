# Development environment

## Supported baseline

- Python 3.12
- uv 0.11 or newer
- Node.js 24 or newer
- npm 11 or newer
- GNU Make
- Git
- Docker Engine with Docker Compose v2
- curl

Linux and macOS are the initial supported development systems. Windows is
supported through WSL2 with Docker Desktop integration.

## First run

    cp .env.example .env
    make doctor
    make bootstrap
    make verify
    make demo

make bootstrap installs locked Python and web dependencies and starts
PostgreSQL plus the OpenTelemetry Collector. It also installs the repository's
pre-commit quality hook. An existing custom hook is never overwritten.

## Start the complete stack

    make dev

Services:

- API: http://localhost:8000
- API documentation: http://localhost:8000/docs
- UI: http://localhost:3000
- PostgreSQL: localhost:5432
- OTLP gRPC: localhost:4317
- OTLP HTTP: localhost:4318
- Collector health: localhost:13133

Stop services without deleting database data:

    make stop

## Verification

    make verify

This runs:

- Ruff formatting and lint;
- strict mypy on production Python;
- Python unit tests;
- React/TypeScript lint;
- web unit tests;
- production web build;
- real PostgreSQL repository, migration, concurrency, and restart integration;
- branch coverage across the complete Python suite.

The integration test expects:

    JARVIS_TEST_DATABASE_URL=postgresql://jarvis:jarvis@localhost:5432/jarvis

The Makefile supplies the local database through TEST_DATABASE_URL. CI overrides
it with its isolated jarvis_test database. Integration tests create and remove
their own uniquely named schemas; they never reset the configured public schema.

Example:

    make verify TEST_DATABASE_URL=postgresql://jarvis:jarvis@localhost:5432/jarvis

## Database migrations

    make migrate

Migrations are immutable SQL files packaged with the application. Startup applies
them under a PostgreSQL advisory lock, records their checksums, and refuses to run
if an already-applied migration was edited. Create a new numbered migration for
every schema change.

## Disposable demo

    make demo

The demo uses an isolated Compose project and host PostgreSQL port 55432,
builds all images, verifies API readiness, submits the deterministic M0 request,
checks the UI, and removes its containers and volume afterward.

## Troubleshooting

Run make doctor first. It reports every missing tool rather than failing on the
first one.

If port 5432 is occupied, set another host port for development:

    POSTGRES_PORT=55432 make bootstrap

When doing so, also set DATABASE_URL and TEST_DATABASE_URL to the same host port.

No paid model credentials are used in M0. Do not add secrets to .env.example,
tests, logs, or Git.
