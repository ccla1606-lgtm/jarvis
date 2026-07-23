# Instructions for coding agents

This file is the durable operating contract for every coding agent working in
this repository.

## Source-of-truth order

When instructions conflict, use this order:

1. accepted GitHub issue and explicit human decisions;
2. docs/DECISIONS.md;
3. docs/ARCHITECTURE.md;
4. docs/IMPLEMENTATION_PLAN.md;
5. docs/MODULE_ACCEPTANCE.md and docs/TEST_STRATEGY.md;
6. local module documentation.

Do not silently reconcile a contradiction. Stop, describe the conflict, and
request a decision.

## Required workflow

1. Work on one GitHub issue at a time.
2. Read the issue, linked architecture sections, and acceptance criteria.
3. Inspect existing code and tests before editing.
4. Write a short implementation plan for the issue.
5. Implement the smallest complete vertical change.
6. Add or update tests with the implementation.
7. Run the narrow tests while developing.
8. Run make verify before declaring completion.
9. Run make demo when the change touches an MVP path.
10. Review the diff for scope creep, secrets, dead code, and architecture leaks.
11. Report commands run, results, and remaining risks.

## Engineering rules

- Domain and application modules must not import provider SDKs, LangSmith SDKs,
  CLI-specific code, web frameworks, or database clients.
- PostgreSQL is the canonical source of task state. Prompts, LangGraph state,
  LangSmith threads, terminal sessions, and UI caches are projections.
- External systems are accessed through typed ports and adapters.
- Every external call has a timeout, classified errors, bounded retries, and
  cancellation behavior.
- Every loop has an explicit iteration, time, and cost limit.
- Side effects require an idempotency key.
- High-risk or scope-expanding actions require human approval.
- Context selection is deterministic and policy-controlled. An LLM may suggest
  context candidates but cannot override access or budget rules.
- Never log secrets, provider credentials, full private prompts, or unrestricted
  tool output.
- Do not add infrastructure, services, frameworks, or abstraction layers unless
  required by the active issue.
- Do not implement post-MVP features while completing an MVP issue.

## Provider portability

- Use logical model profiles in application code.
- Resolve a profile to provider, model, and account only inside the model layer.
- Keep a capability matrix for structured output, tool calls, streaming,
  cancellation, reasoning controls, and context limits.
- Provider-specific features require an explicit native escape hatch in the
  adapter; do not leak provider response objects into domain code.
- Deterministic tests use fake providers. Credential-backed tests run only in
  the live smoke lane.

## Coding-agent adapters

- OMP is the first adapter, not the domain interface.
- Prefer stable RPC, SDK, or agent protocol integration.
- PTY parsing is a fallback and must have contract tests for every supported CLI
  version.
- A coding agent receives a bounded task, selected context, allowed tools,
  resource limits, and a completion contract.
- An agent result is not accepted until an independent verifier checks it.

## Test policy

- A bug fix needs a failing regression test before or with the fix.
- Tests must assert behavior, not implementation details.
- No network or paid model calls in the default make verify path.
- Do not hide flaky tests with retries. Diagnose and remove the source of
  nondeterminism.
- Mocks cannot satisfy an acceptance criterion that explicitly requires
  PostgreSQL, a container, a real CLI process, or a credential-backed provider.

## Forbidden completion shortcuts

A task must be returned to development when any of these are present:

- TODO, pass, NotImplementedError, or fake success on the accepted path;
- skipped required tests;
- tests that do not execute the changed behavior;
- unbounded retry, recursion, or agent spawning;
- direct provider or CLI dependencies outside adapters;
- state held only in memory or prompts;
- secrets in source, fixtures, logs, traces, or artifacts;
- undocumented schema or API changes;
- a failing make verify or required make demo;
- unexplained deviation from the accepted issue.

## Definition of done

An issue is done only when:

- all acceptance criteria are demonstrated;
- required tests pass;
- migrations and rollback behavior are documented when data changes;
- telemetry covers the new external boundary;
- documentation matches behavior;
- the diff contains no unrelated changes;
- the final report includes evidence and known limitations.

