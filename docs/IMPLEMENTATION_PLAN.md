# Step-by-step implementation plan

## 1. Delivery model

Implementation proceeds through twelve delivery gates: M0 through M4, the
integration-closure gate M4.1, the control-plane insertion M4.5, and M5 through
M9. Each gate must leave the repository runnable and must not depend on
incomplete future modules for its own implementation evidence.

The critical path is:

    M0 -> M1 -> M2 -> M3 -> M4 -> M4.1 -> M4.5 -> M5 -> M6 -> M7 -> M8 -> M9

Small UI and documentation tasks may run in parallel after M4, but milestone
acceptance remains sequential on the critical path.

## 2. Audited status baseline

The 2026-07-24 evidence audit establishes separate implementation,
integration-evidence, and release-evidence frontiers:

| Gate | Implementation | Integration/evidence | Release result |
| --- | --- | --- | --- |
| M0 | merged PR #13 | complete | ACCEPTED |
| M1 | merged PR #14 | complete | ACCEPTED |
| M2 | merged PR #15 | live GPT and DeepSeek smoke missing | IMPLEMENTED, RELEASE BLOCKED |
| M3 | merged PR #16 | graph tests pass, default API/demo wiring not proven | IMPLEMENTED, INTEGRATION BLOCKED |
| M4 | merged PR #17 | API tests pass, full M3-to-M4 vertical path not proven | IMPLEMENTED, INTEGRATION BLOCKED |
| M4.1 | not implemented | no evidence | NEXT |
| M4.5 | not implemented | no evidence | NOT STARTED |
| M5-M9 | not implemented | no evidence | NOT STARTED |

The implementation frontier is M4. The strict release-accepted frontier is M1
until issue #3 contains successful credential-backed evidence for both provider
families. M4 SSE is resumable through durable batches and Last-Event-ID; it is
not yet a long-held push connection. No M5 branch or Agent Host implementation
was found in the audit.

Status uses three independent fields:

- implementation: NOT_STARTED, IN_PROGRESS, IMPLEMENTED, or NEEDS_REVISION;
- integration: NOT_STARTED, IN_PROGRESS, ACCEPTED, or BLOCKED;
- release evidence: INCOMPLETE, BLOCKED_EXTERNAL, or COMPLETE.

Only IMPLEMENTED plus integration ACCEPTED, complete release evidence, and
accepted dependencies produces RELEASE_ACCEPTED. Downstream implementation may
proceed past a BLOCKED_EXTERNAL dependency only through an explicit operator
decision stating why the blocker cannot invalidate the next contract. M9 remains
blocked until every mandatory live gate passes.

## 3. Universal Definition of Ready

An implementation issue is ready only when:

- its goal and user-visible result are explicit;
- predecessor implementation is complete, and any integration or external
  evidence blocker is either closed or explicitly waived for downstream
  implementation by the operator without waiving release evidence;
- owned modules and prohibited modules are named;
- inputs, outputs, errors, and state transitions are specified;
- acceptance scenarios are testable;
- required external credentials are either available for a live lane or clearly
  excluded from deterministic CI;
- unresolved decisions that could change the implementation are closed.

If any item is missing, the issue stays blocked and no production code is
written.

## 4. Universal Definition of Done

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

A completion report must state implementation, integration, and release-evidence
status separately. The word "done" without all three statuses is not an
accepted milestone result.

## 5. Milestone transition protocol

Before a coding agent starts a gate or work package it must:

1. name the exact issue, gate, package, and source commit;
2. reproduce predecessor exit evidence or cite the accepted evidence packet;
3. list owned modules and modules that must not change;
4. list input/output schemas, state transitions, stable errors, migrations,
   telemetry, and tests;
5. resolve every decision that could change persistence, API, or security;
6. map implementation steps one-to-one to acceptance scenarios.

During implementation the agent works on one package, keeps the repository
runnable, and cannot silently begin a later package.

The next package becomes READY only when the current package's mandatory
deterministic tests, migrations, documentation, and evidence pass. A gate is
INTEGRATION-ACCEPTED only when the real module path is wired and proven. A
release gate is closed only when mandatory live evidence and dependencies also
pass. Any ambiguity, failed mandatory gate, unreproducible evidence, or
active-path stub returns the package to NEEDS_REVISION.

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

## M4.1. Integration closure for the existing brain and API

### Goal

Prove the already merged M3 graph and M4 API operate as one real vertical slice.
This is a correction gate, not a new product feature.

### Entry gate

- M3 and M4 implementation commits are present on the source branch;
- their isolated unit, integration, and API evidence is reproducible;
- the operator accepts the documented M2 live-smoke blocker as external and
  separate from this integration work.

### Deliverables

- default application composition wires the typed brain runtime into the API;
- task submission follows the real triage route rather than a placeholder-only
  path;
- planned requests reach durable `AWAITING_APPROVAL` with an exact Plan version;
- fast read-only requests complete without an approval;
- approval, rejection, cancel, retry, restart, and event reconstruction work
  through the same running application;
- `make demo` exercises the real API -> graph -> PostgreSQL path twice;
- the SSE contract explicitly documents reconnectable durable batches versus a
  future long-held push stream.

### Acceptance tests

1. A simple request through the deployed API reaches the fast path and persists
   its terminal result.
2. A complex side-effecting request through the deployed API reaches
   `AWAITING_APPROVAL` and persists its exact Plan version.
3. Approval through the API creates the expected Run/ApprovedExecutionSpec
   boundary without bypassing application services.
4. Rejection creates no Run.
5. API restart while awaiting approval preserves the task and allows a valid
   approval.
6. Duplicate submit, approve, cancel, and retry commands remain idempotent.
7. SSE reconnect from `Last-Event-ID` returns no duplicate transitions.
8. `make demo` passes twice with real PostgreSQL and the configured graph runtime.

### Return to development when

- default API composition uses a null or placeholder brain on the accepted path;
- demo checks only `RECEIVED` instead of the route required by the request;
- API and graph use different repositories or state machines;
- approval/retry bypasses the exact persisted Plan version;
- a passing unit test is used as evidence for an unwired production path.

### Transition to M4.5

M4.1 is INTEGRATION-ACCEPTED when all eight scenarios pass from a clean
checkout, the real runtime composition is documented, and the current M2 live
blocker remains explicitly open rather than hidden. M4.5 may then add the
operator-direction contracts without guessing how the API/graph path is wired.

## M4.5. Operator direction and agent control

### Goal

Add the durable single-operator control model before a real executor is
connected: Projects, immutable Goal revisions, versioned AgentProfiles,
content-addressed approval and execution contracts, and proposal-driven agent
evolution.

### Entry gate

- M4.1 is INTEGRATION-ACCEPTED;
- the M2 live-smoke blocker is recorded as external and explicitly separated
  from M4.5 deterministic contracts;
- every unresolved persistence, API, and security decision in
  [the M4.5 execution specification](M4_5_EXECUTION_SPEC.md) is closed.

### Ordered work packages

1. M4.5-0 baseline and contract freeze;
2. M4.5-1 pure domain model;
3. M4.5-2 PostgreSQL persistence and migration from M4;
4. M4.5-3 application use cases;
5. M4.5-4 ApprovedExecutionSpec and ExecutionEnvelope integration;
6. M4.5-5 versioned API and projections;
7. M4.5-6 controlled evaluation, promotion, and rollback;
8. M4.5-7 demo, documentation, and evidence.

Agents must execute these packages in order and use the owned/prohibited modules,
actions, tests, and exit evidence in the linked specification.

### Deliverables

- Project and Goal with immutable GoalRevision;
- idempotent OperatorBootstrap with versioned Personal Project, Inbox Goal, and
  default assistant profile for omitted fast read-only scope;
- AgentProfile with immutable AgentProfileVersion;
- ChangeProposal and append-only EvaluationEvidence;
- immutable ApprovedExecutionSpec created by approval;
- content-addressed ExecutionEnvelope as CodingExecutorPort input;
- idempotent versioned commands, repositories, migrations, API, projections, and
  stable errors;
- deterministic promotion and rollback controlled by the operator;
- updated demo and evidence packet.

### Acceptance tests

1. Planned or side-effecting work cannot be approved without an explicit active
   Goal and an eligible exact AgentProfileVersion.
2. Omitted fast read-only scope resolves to persisted built-in versions; new
   canonical Tasks never store null direction or behavior.
3. Goal and profile edits create immutable versions and never alter prior Runs.
4. Hierarchy cycles, stale versions, invalid transitions, and scope expansion are
   rejected without partial state.
5. One active profile version is enforced under concurrent promotion.
6. Approval creates a stable digest over every material execution field.
7. Envelope reconstruction after restart produces the same digest; tampering is
   rejected.
8. Retry creates a new Run and envelope while preserving all prior evidence.
9. Missing or failing evaluation evidence blocks promotion.
10. An agent-originated proposal cannot approve, promote, apply, or roll back
   itself.
11. Migration from M4 and empty state, OpenAPI, UI fixtures, make verify, and
    make demo twice all pass.

### Transition to M5

M5 is READY only when all M4.5 packages and acceptance tests pass, the envelope
schema is versioned, and a recording executor consumes it without needing domain
changes. The M2 live blocker may remain open for implementation only; it remains
a release blocker.

### Return to development when

- direction or active behavior exists only in prompts or configuration files;
- versions or evidence can be edited in place;
- side-effecting work can be unscoped;
- approval does not bind goal, profile, tools, budgets, and verification;
- CodingExecutorPort accepts an ad-hoc dictionary or raw prompt;
- promotion or rollback is possible without operator authorization;
- an M4.5 package skips its predecessor exit gate.

Full field contracts, invariants, API commands, ordered steps, and package exit
criteria are canonical in
[docs/M4_5_EXECUTION_SPEC.md](M4_5_EXECUTION_SPEC.md).

## M5. Agent Host and first OMP coding executor

### Goal

Run one approved, content-addressed ExecutionEnvelope in an isolated process and
normalize its lifecycle.

### Entry gate

- M4.1 is integration-accepted;
- M4.5 deterministic contracts and migrations are accepted;
- CodingExecutorPort and envelope schema are frozen and versioned;
- a recording executor proves exact scope, profile, budget, and digest handoff.

### Deliverables

- CodingExecutorPort implementation without changing its M4.5 domain contract;
- Agent Host service/process;
- OMP adapter through the most stable available RPC, SDK, or protocol;
- PTY fallback only if necessary;
- canonical workspace realpath plus explicit symlink/path-traversal policy;
- workspace, tool, and command allowlists;
- minimal subprocess environment;
- at-most-one active launch per run attempt;
- persisted/replayable events and deterministic cancel/completion precedence;
- start, events, status, cancel, timeout, reconcile, and result collection;
- immutable artifact manifest with digests;
- normalized executor error taxonomy.

### Acceptance tests

1. An altered, stale, unsupported, or over-budget envelope is rejected before a
   child process starts.
2. A fixture coding task uses the exact AgentProfileVersion and edits only the
   allowed workspace.
3. Events are streamed in order with project, goal, task, profile, and run
   correlation IDs.
4. Successful completion returns result and artifact digests.
5. Timeout terminates the child process and reports a classified failure.
6. Cancel terminates the entire process tree and is idempotent.
7. Agent Host restart marks or recovers orphaned runs deterministically.
8. Attempts to access a disallowed path are blocked and audited.
9. Secrets not explicitly allowlisted are absent from the child environment.
10. CLI version mismatch fails clearly instead of silently parsing wrong output.
11. A real OMP smoke scenario completes in a disposable test repository.

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

- ContextRequest derived from ApprovedExecutionSpec and immutable ContextManifest;
- explicit Project, GoalRevision, profile, repository, and artifact scopes;
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
- automated EvaluationRun support for ChangeProposals and profile candidates;
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
- Project and Goal hierarchy, status, budget, and evidence views;
- AgentProfile version, candidate, promotion, and rollback views;
- ChangeProposal and evaluation comparison views;
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
13. Duplicate Project, Goal, promotion, rollback, submit, approve, cancel, and
    retry commands remain idempotent.
14. Profile promotion does not change a historical Run, and rollback restores an
    eligible version without deleting evidence.
15. A SYSTEM Project Goal produces a fully scoped, approved, verified task.
16. Fresh clone can run bootstrap, verify, and demo from documentation alone.

### Release gate

The MVP can be released only when:

- every M0-M4, M4.1, M4.5, and M5-M9 issue is closed with evidence;
- all deterministic tests pass on the protected branch;
- live smoke tests pass for two provider families and OMP;
- there are no critical or high unaccepted security findings;
- no active-path stub, skipped required test, or undocumented manual step exists;
- backup restore has been exercised;
- known limitations are documented.

### Return to development when

Any release gate is missing, flaky, bypassed, or supported only by a
natural-language claim.

## 6. Post-MVP order

Only after M9:

1. second coding CLI adapter;
2. scheduled and proactive tasks;
3. richer bounded memory;
4. multi-repository task support;
5. stronger sandbox backend;
6. concurrency queue based on measured load;
7. optional self-hosted observability backend;
8. enterprise identity and multi-tenancy.

