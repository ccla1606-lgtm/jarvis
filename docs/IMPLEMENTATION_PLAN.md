# Step-by-step implementation plan

## 1. Delivery model

Implementation proceeds through ten milestones, M0 through M9. Each milestone
must leave the repository runnable and must not depend on incomplete future
modules for its own acceptance.

The critical path is:

    M0 -> M1 -> M2 -> M3 -> M4 -> M5 -> M6 -> M7 -> M8 -> M9

Small UI and documentation tasks may run in parallel after M4, but milestone
acceptance remains sequential on the critical path.

## 2. Universal Definition of Ready

An implementation issue is ready only when:

- its goal and user-visible result are explicit;
- dependencies are closed or available;
- owned modules and prohibited modules are named;
- inputs, outputs, errors, and state transitions are specified;
- acceptance scenarios are testable;
- required external credentials are either available for a live lane or clearly
  excluded from deterministic CI;
- unresolved decisions that could change the implementation are closed.

If any item is missing, the issue stays blocked and no production code is
written.

## 3. Universal Definition of Done

Every milestone must provide:

- working implementation without active-path stubs;
- unit tests for rules and edge cases;
- contract tests for every new port or API boundary;
- integration tests for every real infrastructure boundary;
- correlated telemetry for new external calls;
- documentation and configuration examples;
- successful deterministic CI;
- a completion report with commands and evidence.

Any user-visible MVP path change must also pass make demo.

## M0. Repository and executable development environment

### Goal

Create a repository that a coding agent can bootstrap, run, verify, and diagnose
without undocumented manual steps.

### Deliverables

- Python project with pinned dependency strategy;
- React and TypeScript application;
- Docker Compose with PostgreSQL and OpenTelemetry Collector;
- Makefile implementing doctor, bootstrap, dev, verify, and demo;
- environment example without secrets;
- formatter, linter, type checker, unit-test runner, and pre-commit hooks;
- CI workflow for deterministic checks;
- health endpoints and placeholder UI health page;
- documented supported operating systems.

### Acceptance tests

1. Fresh clone plus make bootstrap succeeds.
2. make doctor reports actionable errors when Docker or configuration is missing.
3. make dev starts the stack and both health endpoints become ready.
4. make verify succeeds with network access disabled after dependencies are present.
5. make demo performs a local placeholder request and exits successfully.
6. No generated dependency directory or secret is tracked by Git.
7. The same commands work twice without manual cleanup.

### Return to development when

- any required command is a documentation-only placeholder;
- setup depends on an undocumented global package;
- the second bootstrap or dev run fails;
- CI and local commands execute different test sets;
- health reports ready before PostgreSQL is usable.

## M1. Domain contracts and durable state

### Goal

Implement canonical entities, state transitions, database schema, and
transactional repositories.

### Deliverables

- typed identifiers and entities for Task, Plan, Run, Approval, Artifact,
  ModelResolution, and TraceLink;
- declared task state machine;
- PostgreSQL migrations;
- repository ports and PostgreSQL adapters;
- optimistic concurrency and idempotency support;
- append-only transition history;
- fake in-memory repositories for unit tests only.

### Acceptance tests

1. Every allowed state transition succeeds.
2. Every undeclared transition is rejected without changing state.
3. Duplicate command with the same idempotency key returns the original result.
4. Two concurrent updates produce one winner and one classified conflict.
5. Approval for plan version N cannot execute plan version N+1.
6. Retry creates a new Run while preserving previous attempts.
7. Repository state survives API process restart.
8. Migrations create a working database from empty state.

### Return to development when

- business rules exist only in API handlers or graph nodes;
- state is stored only in LangGraph checkpoints;
- retry overwrites prior evidence;
- idempotency is tested only with a mock repository;
- schema changes lack migration coverage.

## M2. Provider-agnostic model gateway

### Goal

Support multiple LLM provider families without leaking provider SDKs into
domain, application, or graph modules.

### Deliverables

- ModelPort and normalized request/response contracts;
- logical model profiles;
- capability matrix;
- routing and fallback policy;
- GPT-family adapter;
- DeepSeek-family or OpenAI-compatible adapter;
- normalized usage and ModelResolution records;
- fake provider for deterministic tests;
- separate credential-backed smoke-test command.

### Acceptance tests

1. The same model contract suite passes for every adapter.
2. Structured output is validated against the requested schema.
3. Invalid structured output receives at most the configured bounded repair.
4. Timeout, 401, 429, 5xx, and context overflow are classified.
5. Retry occurs only for retryable categories and respects maximum attempts.
6. Fallback records the reason and actual provider/model.
7. Cancellation stops streaming and releases resources.
8. No credential or provider response object crosses the adapter boundary.
9. Live smoke tests prove one successful call to two provider families.

### Return to development when

- application code selects raw provider model names;
- fallback happens after partial output without a new attempt;
- fake providers are presented as proof of live compatibility;
- unsupported capabilities silently degrade;
- secrets appear in logs or exception text.

## M3. LangGraph brain: triage, fast answer, and planning

### Goal

Implement the decision graph for fast, bounded, and planned requests.

### Deliverables

- typed graph state derived from domain identifiers;
- deterministic route validation;
- triage node;
- fast-answer node;
- bounded-task node;
- typed planner producing a finite step plan;
- graph-level budgets for steps, tokens, time, and repair;
- direct local runtime and runtime adapter boundary;
- graph visualization available in development.

### Acceptance tests

1. A simple request follows the fast path and creates no approval.
2. A complex side-effecting request produces a finite typed plan.
3. Invalid route output fails safely or uses one bounded repair.
4. A plan with a cycle, missing dependency, or excess scope is rejected.
5. Maximum step, token, and time budgets stop execution.
6. Replaying the same stored task resumes from the persisted state.
7. The graph runs without LangSmith and without production Agent Server.
8. Graph nodes do not import provider or subprocess SDKs.

### Return to development when

- LLM text directly selects an unvalidated function;
- the graph contains an unbounded loop;
- task state exists only inside graph state;
- disabling LangSmith breaks execution;
- a plan can expand tool or repository scope without approval.

## M4. API and approval workflow

### Goal

Expose versioned task commands, queries, event streaming, and human approval.

### Deliverables

- versioned REST endpoints defined in architecture;
- idempotency middleware or command handling;
- approval and rejection endpoints bound to immutable plan versions;
- cancellation and retry endpoints;
- Server-Sent Events for task updates;
- consistent error envelope and correlation ID;
- generated OpenAPI artifact;
- basic development authentication boundary.

### Acceptance tests

1. Submitting the same idempotent request twice creates one Task.
2. Approval starts only the approved plan version.
3. Rejection creates no coding run.
4. Cancel can be called repeatedly with the same final result.
5. Retry creates a new attempt and preserves previous history.
6. SSE reconnect resumes without duplicating state transitions.
7. Invalid payload and invalid transition return stable error codes.
8. API process restart does not lose an awaiting approval task.
9. OpenAPI schema matches response fixtures used by the UI client.

### Return to development when

- endpoints bypass application use cases;
- HTTP status and error codes change nondeterministically;
- approval is inferred from conversation text;
- SSE is the only source of state;
- API logs expose request secrets.

## M5. Agent Host and first OMP coding executor

### Goal

Run one bounded coding task in an isolated process and normalize its lifecycle.

### Deliverables

- CodingExecutorPort;
- Agent Host service/process;
- OMP adapter through the most stable available RPC, SDK, or protocol;
- PTY fallback only if necessary;
- workspace allowlist;
- minimal subprocess environment;
- start, events, status, cancel, timeout, and result collection;
- immutable artifact manifest with digests;
- normalized executor error taxonomy.

### Acceptance tests

1. A fixture coding task edits only the allowed workspace.
2. Events are streamed in order with task and run correlation IDs.
3. Successful completion returns result and artifact digests.
4. Timeout terminates the child process and reports a classified failure.
5. Cancel terminates the entire process tree and is idempotent.
6. Agent Host restart marks or recovers orphaned runs deterministically.
7. Attempts to access a disallowed path are blocked and audited.
8. Secrets not explicitly allowlisted are absent from the child environment.
9. CLI version mismatch fails clearly instead of silently parsing wrong output.
10. A real OMP smoke scenario completes in a disposable test repository.

### Return to development when

- production behavior is validated only with a fake subprocess;
- cancel leaves a child process running;
- terminal text parsing is unversioned or untested;
- artifacts can change after their digest is recorded;
- OMP session IDs become canonical Jarvis run IDs.

## M6. Context compiler and bounded memory

### Goal

Provide each model or coding agent only the context required for its task.

### Deliverables

- ContextRequest and immutable ContextManifest;
- explicit source scopes;
- retrieval and ranking strategy;
- trust and access labels;
- provider-aware token counting;
- deduplication and hard packing budget;
- approved task summary storage;
- selected/excluded source explanation;
- stable manifest digest.

### Acceptance tests

1. Explicitly referenced relevant files are included.
2. Unrelated files are excluded under a constrained budget.
3. Disallowed files never enter prompt or artifact output.
4. Duplicate content is counted once.
5. Manifest token estimate stays below the target provider limit.
6. The same immutable inputs produce the same manifest digest.
7. Provider change recompiles packing without changing task scope.
8. Poisoning instructions inside retrieved content cannot modify policy.
9. Compaction preserves required acceptance criteria and unresolved errors.
10. Deleted or revoked context is not returned in a new manifest.

### Return to development when

- an autonomous context agent can override access rules;
- context selection cannot explain exclusions;
- token budget is estimated only by string length;
- entire repository contents are sent by default;
- summaries become trusted facts without approval or provenance.

## M7. Verification and bounded repair

### Goal

Independently verify agent results and allow only finite, evidence-based repair.

### Deliverables

- VerifierPort;
- deterministic command verifier;
- optional reviewer model profile;
- evidence bundle;
- bounded repair policy;
- NEEDS_REVISION transition and failure reasons;
- artifact and diff review hooks.

### Acceptance tests

1. Passing implementation with required evidence reaches SUCCEEDED.
2. Failing required command reaches NEEDS_REVISION.
3. Missing evidence cannot be interpreted as success.
4. Repair receives only failure evidence and remaining task context.
5. Repair stops at configured attempt, cost, and time limits.
6. Reviewer disagreement is recorded and resolved by deterministic gates.
7. A malicious agent-written test cannot replace mandatory platform gates.
8. Prior failed attempts remain visible.

### Return to development when

- the implementing agent approves its own work without independent checks;
- repair loops until success;
- verification relies only on natural-language claims;
- required failures are downgraded to warnings;
- evidence is mutable.

## M8. OpenTelemetry and operator UI

### Goal

Make tasks, plans, agent activity, cost, errors, and traces observable and
operable from one UI.

### Deliverables

- OpenTelemetry spans across API, graph, model, context, and executor;
- trace correlation through task_id, plan_id, and run_id;
- structured redacted logs;
- latency, token, cost, failure, retry, and queue metrics;
- task list and state filters;
- task detail timeline;
- plan approval and rejection controls;
- cancel and retry controls;
- artifacts and trace links;
- disconnected/reconnect UI behavior.

### Acceptance tests

1. One end-to-end task produces a connected trace across all active modules.
2. Every external call records duration, outcome, and classified error.
3. Secrets and blocked content are absent from exported telemetry.
4. UI refresh reconstructs state from the API.
5. Event-stream reconnect does not duplicate timeline entries.
6. Stale approval controls are rejected by version.
7. Cancel and retry UI actions show deterministic final state.
8. Provider and model resolution is visible without exposing account secrets.
9. LangSmith exporter can be disabled while local OTel traces remain.

### Return to development when

- UI maintains canonical state not present in the API;
- traces cannot correlate an executor run to a task;
- raw prompts or credentials are exported;
- a failed action appears successful until page refresh;
- observability requires one proprietary backend.

## M9. End-to-end hardening and MVP release

### Goal

Prove the complete MVP under success, failure, restart, cancellation, and
provider-switch scenarios.

### Deliverables

- complete make demo scenario;
- deterministic CI matrix;
- live provider and OMP smoke workflow;
- backup and restore runbook for PostgreSQL and artifacts;
- migration and rollback runbook;
- security and dependency scan;
- release checklist and versioned configuration;
- documented limitations and post-MVP backlog.

### Required end-to-end scenarios

1. Fast answer succeeds with the primary provider.
2. Primary provider timeout falls back according to policy.
3. Complex request creates a plan, waits, is approved, executes, verifies, and
   succeeds.
4. Rejected plan never starts an executor.
5. Cancellation during model streaming reaches CANCELLED.
6. Cancellation during coding execution terminates the process tree.
7. API restart while awaiting approval preserves the task.
8. Agent Host restart produces deterministic recovery or classified failure.
9. Failed verification produces NEEDS_REVISION and one bounded repair.
10. Provider switch preserves task and context scope.
11. Telemetry exporter outage does not lose canonical task state.
12. Disallowed workspace access is blocked and audited.
13. Duplicate submit, approve, cancel, and retry commands remain idempotent.
14. Fresh clone can run bootstrap, verify, and demo from documentation alone.

### Release gate

The MVP can be released only when:

- every M0-M9 issue is closed with evidence;
- all deterministic tests pass on the protected branch;
- live smoke tests pass for two provider families and OMP;
- there are no critical or high unaccepted security findings;
- no active-path stub, skipped required test, or undocumented manual step exists;
- backup restore has been exercised;
- known limitations are documented.

### Return to development when

Any release gate is missing, flaky, bypassed, or supported only by a
natural-language claim.

## 4. Post-MVP order

Only after M9:

1. second coding CLI adapter;
2. scheduled and proactive tasks;
3. richer bounded memory;
4. multi-repository task support;
5. stronger sandbox backend;
6. concurrency queue based on measured load;
7. optional self-hosted observability backend;
8. enterprise identity and multi-tenancy.

