# Instructions for coding agents

This file is the durable operating contract for every coding agent working in
this repository.

## Source-of-truth order

When instructions conflict, use this order:

1. accepted GitHub issue and explicit human decisions;
2. docs/DECISIONS.md;
3. docs/ARCHITECTURE.md;
4. docs/IMPLEMENTATION_PLAN.md;
5. the execution specification linked by the active milestone, including
   docs/M4_5_EXECUTION_SPEC.md for M4.5;
6. docs/MODULE_ACCEPTANCE.md and docs/TEST_STRATEGY.md;
7. local module documentation.

Do not silently reconcile a contradiction. Stop, describe the conflict, and
request a decision.

## Required workflow

1. Work on one GitHub issue and one declared work package at a time.
2. Read the issue, current status baseline, linked architecture sections,
   execution specification, and acceptance criteria.
3. State predecessor implementation, integration-evidence, and release-evidence
   status separately; never collapse them into the word "done".
4. Inspect existing code, migrations, API schemas, and tests before editing.
5. List exact owned modules, prohibited modules, inputs, outputs, transitions,
   errors, migrations, telemetry, and evidence for the work package.
6. Stop and request an operator decision if any contract is ambiguous or
   conflicts with a higher-priority source.
7. Write a short implementation plan mapped one-to-one to acceptance tests.
8. Implement the smallest complete vertical change without starting the next
   package.
9. Add or update tests with the implementation.
10. Run narrow tests while developing.
11. Run make verify before declaring implementation complete.
12. Run make demo when the change touches an MVP path.
13. Review the diff for scope creep, secrets, dead code, mutable evidence, and
   architecture leaks.
14. Report commands, results, implementation/evidence status, blockers, and the
   exact transition gate for the next package.

## Milestone transition protocol

Before writing production code, an agent must produce a readiness statement:

- active stage and work-package identifier;
- predecessor implementation, integration-evidence, and release-evidence status;
- exact source commit;
- dependencies and external blockers;
- owned and prohibited modules;
- inputs, outputs, transitions, stable errors, migrations, telemetry, and tests;
- unresolved decisions, which must be empty.

A package is READY only when all contracts are explicit and its predecessor exit
evidence is reproducible. A downstream package may proceed past an isolated
external live-test blocker only after an explicit operator decision records why
that blocker cannot invalidate the downstream contract. The blocker remains open
for release.

A package is IMPLEMENTED only when deterministic code, tests, migrations,
documentation, and evidence pass. It is INTEGRATION-ACCEPTED only when the real
module path is wired and proven. It is RELEASE-ACCEPTED only when mandatory
external evidence and dependency release gates also pass. Agents must use these
terms exactly.

## Single-operator control rules

- WORK and SYSTEM direction is represented by Project and immutable GoalRevision
  records; hidden prompt-only goals are prohibited.
- Planned or side-effecting Tasks require active Goal scope.
- Runs bind exact AgentProfileVersion and ApprovedExecutionSpec digests.
- Agents may draft goals, profile versions, and ChangeProposals, but only the
  operator may approve material scope, promotion, application, rollback, or goal
  completion.
- Active profiles, approved scopes, execution envelopes, evidence records, and
  historical Runs are never edited in place.
- Self-modification means proposal plus evaluation plus operator decision, not
  direct mutation.

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
- CodingExecutorPort receives only a validated immutable ExecutionEnvelope.
- A coding agent receives a bounded task, exact goal and profile versions,
  selected context, allowed tools, resource limits, and a completion contract.
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
- state, system direction, or active agent behavior held only in memory or prompts;
- an unscoped planned or side-effecting Task;
- direct mutation or self-approval of an active AgentProfileVersion;
- execution that does not verify the ApprovedExecutionSpec and envelope digest;
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
- the final report includes implementation, integration, and release evidence,
  known limitations, remaining blockers, and the exact readiness decision for the
  next work package.

