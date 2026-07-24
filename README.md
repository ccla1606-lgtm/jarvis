# Jarvis

Jarvis is a provider-agnostic personal assistant and coding-agent orchestration platform.

The first release is intentionally a production-shaped MVP: it keeps clean module
boundaries, durable state, tests, traces, and replaceable adapters, while avoiding
premature distributed infrastructure.

## MVP outcome

The MVP is complete when its single operator can:

1. define WORK or SYSTEM Projects and measurable versioned Goals;
2. define versioned AgentProfiles with explicit tools, context, budgets, and
   verification policy;
3. submit a request linked to an active Goal;
4. receive a fast answer for a simple read-only request;
5. receive an explicit plan for a complex request;
6. approve or reject one immutable execution scope;
7. run the approved coding task through one CLI coding-agent adapter;
8. cancel or retry the run without losing prior evidence;
9. inspect task state, agent actions, artifacts, logs, costs, and traces in the UI;
10. evaluate, promote, and roll back agent-profile versions through explicit
    evidence and operator approval;
11. switch between at least two LLM provider families without changing domain code.

## Current delivery status

As audited on 2026-07-24, the implementation frontier on `main` is M4:
M0 and M1 are accepted, M2 implementation is complete but its required
two-provider credential-backed live smoke remains externally blocked, and M3/M4
code is merged with isolated deterministic evidence. The M3 graph is not yet
wired into the default API/demo path, so the system-level vertical slice is not
accepted. M5 has not started. M4.1 integration closure and M4.5 operator control
are the next gates.

Implementation completion, integration-evidence, and release-evidence are
tracked separately. An isolated external live-smoke blocker may permit
downstream implementation after an explicit operator decision, but it never
counts as release evidence.

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

## Repository layout

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
    make migrate
    make verify
    make demo
    make openapi

- make doctor checks required tools and configuration without changing the system.
- make bootstrap installs dependencies and creates the local environment.
- make dev starts API, UI, PostgreSQL, telemetry, and development dependencies.
- make migrate applies immutable PostgreSQL schema migrations.
- make verify runs every deterministic pull-request gate.
- make demo runs a complete local end-to-end scenario.
- make openapi regenerates the reviewed API v1 schema snapshot.

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
- [M4.5 execution specification](docs/M4_5_EXECUTION_SPEC.md)
- [Module acceptance criteria](docs/MODULE_ACCEPTANCE.md)
- [Test strategy](docs/TEST_STRATEGY.md)
- [Architecture decisions](docs/DECISIONS.md)
- [Domain state and persistence](docs/DOMAIN_STATE.md)
- [Model gateway](docs/MODEL_GATEWAY.md)
- [Brain runtime](docs/BRAIN_RUNTIME.md)
- [API v1](docs/API_V1.md)
- [Agent instructions](AGENTS.md)

## Delivery policy

Work is implemented one accepted work package at a time. Each report states
implementation, integration-evidence, and release-evidence status separately. A
milestone is release-accepted only when its code, tests, external evidence,
dependencies, and documentation are complete. Passing unit tests alone is never
sufficient for a module that has external boundaries.
