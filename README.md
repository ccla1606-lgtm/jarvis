# Jarvis

Jarvis is a provider-agnostic personal assistant and coding-agent orchestration platform.

The first release is intentionally a production-shaped MVP: it keeps clean module
boundaries, durable state, tests, traces, and replaceable adapters, while avoiding
premature distributed infrastructure.

## MVP outcome

The MVP is complete when a user can:

1. submit a request;
2. receive a fast answer for a simple request;
3. receive an explicit plan for a complex request;
4. approve or reject that plan;
5. run an approved coding task through one CLI coding-agent adapter;
6. cancel or retry the run;
7. inspect task state, agent actions, artifacts, logs, and traces in the UI;
8. switch between at least two LLM provider families without changing domain code.

## Architecture

- Python, FastAPI, Pydantic, and LangGraph for the modular backend.
- PostgreSQL as the canonical task and workflow state store.
- React and TypeScript for the operator UI.
- OpenTelemetry as the canonical telemetry format.
- LangSmith Studio during development; the runtime remains replaceable.
- LiteLLM or equivalent gateway behavior behind an internal ModelPort.
- Isolated Agent Host processes for OMP and future coding CLI adapters.
- Docker Compose for the reproducible local environment.

LangGraph, LangSmith, LiteLLM, OMP, and individual model providers are adapters
or implementation choices. They do not own Jarvis domain state.

## Planned repository layout

    apps/
      api/
      web/
      agent_host/
    src/jarvis/
      domain/
      application/
      graph/
      models/
      context/
      executors/
      telemetry/
      infrastructure/
    migrations/
    tests/
      unit/
      contract/
      integration/
      e2e/
    docs/

## Command contract

The M0 development environment implements these commands:

    make doctor
    make bootstrap
    make dev
    make verify
    make demo

- make doctor checks required tools and configuration without changing the system.
- make bootstrap installs dependencies and creates the local environment.
- make dev starts API, UI, PostgreSQL, telemetry, and development dependencies.
- make verify runs every deterministic pull-request gate.
- make demo runs a complete local end-to-end scenario.

No implementation task is complete until the relevant checks pass. After M0,
the default completion gate is:

    make verify && make demo

## Quick start

Prerequisites are Python 3.12, Node.js 24+, uv, GNU Make, Docker with Compose,
and curl.

    cp .env.example .env
    make doctor
    make bootstrap
    make verify
    make demo

See [development environment](docs/DEVELOPMENT.md) for service URLs and
troubleshooting.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Implementation plan](docs/IMPLEMENTATION_PLAN.md)
- [Module acceptance criteria](docs/MODULE_ACCEPTANCE.md)
- [Test strategy](docs/TEST_STRATEGY.md)
- [Architecture decisions](docs/DECISIONS.md)
- [Agent instructions](AGENTS.md)

## Delivery policy

Work is implemented one milestone issue at a time. A milestone can be closed
only when its code, tests, evidence, and documentation are present. Passing unit
tests alone is never sufficient for a module that has external boundaries.
