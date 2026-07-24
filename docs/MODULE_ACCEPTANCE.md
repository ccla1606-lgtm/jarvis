# Module acceptance criteria

This document defines the minimum evidence required to accept a module. It is
used by implementers, reviewers, and coding agents.

## Acceptance result

Each review assigns exactly one result:

- ACCEPTED: all mandatory evidence is present and every required gate passes.
- NEEDS_REVISION: implementation is plausible but one or more required gates
  fail or evidence is incomplete.
- BLOCKED: a dependency, credential, decision, or environment prevents valid
  evaluation.
- REJECTED: implementation violates an architectural or security invariant and
  requires redesign rather than a small repair.

## Evidence packet

Every module submission includes:

- issue number and acceptance criteria;
- changed files;
- commands executed;
- test results;
- relevant trace or artifact references;
- migrations and configuration changes;
- known limitations;
- reason for every skipped test.

Missing evidence produces NEEDS_REVISION, not assumed success.

## Domain

### Accept when

- entities and value objects are framework-independent;
- transition rules are explicit and exhaustively tested;
- identifiers are stable and provider-neutral;
- error categories are typed;
- invalid construction is impossible or rejected at the boundary.

### Required tests

- entity construction and serialization;
- all allowed transitions;
- all forbidden transitions;
- equality and identity behavior;
- plan version approval rules;
- run retry history.

### Needs revision when

- business rules are duplicated in handlers;
- raw dictionaries cross domain boundaries;
- provider, database, or web imports exist;
- terminal states can transition without an explicit rule.

## PostgreSQL persistence

### Accept when

- repositories honor application transaction boundaries;
- optimistic concurrency and idempotency work against real PostgreSQL;
- migration from empty database succeeds;
- restart preserves state;
- transitions and prior attempts remain immutable.

### Required tests

- repository contract suite;
- real PostgreSQL integration;
- concurrent writer conflict;
- duplicate command behavior;
- migration smoke;
- restart and re-read.

### Needs revision when

- SQLite or in-memory behavior is the only integration proof;
- transaction rollback leaves partial state;
- retry overwrites previous run;
- a migration requires undocumented manual SQL.

## Model gateway

### Accept when

- all adapters pass the same normalized contract tests;
- capability mismatch is explicit;
- resolution and usage are recorded;
- timeout, retry, fallback, streaming, and cancellation are bounded;
- secrets are redacted.

### Required tests

- fake deterministic unit suite;
- adapter contract suite;
- error classification matrix;
- cancellation test;
- structured output test;
- two-family credential-backed smoke tests.

### Needs revision when

- raw SDK objects escape;
- provider name appears in domain rules;
- unsupported features silently fall back;
- live compatibility is claimed from mocks.

## LangGraph orchestration

### Accept when

- graph state references canonical domain IDs;
- every node calls a typed application port;
- loops and repairs are bounded;
- direct local runtime works;
- persisted task state survives graph runtime restart.

### Required tests

- fast path;
- planned path;
- invalid classifier output;
- invalid or cyclic plan;
- budget exhaustion;
- approval interrupt and resume;
- runtime without LangSmith.

### Needs revision when

- graph checkpoint is canonical business storage;
- a node calls a provider SDK or CLI;
- scope can expand without validation;
- a proprietary trace backend is required to run.

## API

### Accept when

- schemas are versioned and documented;
- commands are idempotent;
- errors are stable and correlated;
- approval binds to a plan version;
- event stream is resumable;
- readiness reflects dependencies.

### Required tests

- OpenAPI schema snapshot or compatibility test;
- command happy and invalid paths;
- idempotency;
- stale approval;
- cancel and retry;
- SSE reconnect;
- API restart.

### Needs revision when

- handlers implement domain decisions;
- error behavior depends on unhandled exceptions;
- readiness returns true with unavailable PostgreSQL;
- event stream is the only durable history.

## Operator direction and agent control

### Accept when

- WORK and SYSTEM Projects use one canonical model;
- Goal direction, agent behavior, approval scope, envelopes, and evidence are
  immutable or append-only versions;
- every planned or side-effecting Task binds an active GoalRevision and exact
  AgentProfileVersion;
- approval creates a content-addressed ApprovedExecutionSpec;
- CodingExecutorPort accepts only a validated ExecutionEnvelope;
- promotion and rollback are evidence-backed, atomic, audited, idempotent, and
  operator-authorized;
- historical Runs remain reproducible after direction or profile changes;
- the real M3-to-M4 API/graph path is proven separately by M4.1.

### Required tests

- Project, Goal, profile, and proposal allowed and forbidden transitions;
- goal hierarchy cycle and cross-project parent rejection;
- immutable revision and canonical digest golden vectors;
- stale version and duplicate command behavior;
- migration from M4 and from empty PostgreSQL;
- restart and exact scope reconstruction;
- concurrent profile promotion with one winner;
- missing/failing evidence blocks promotion;
- agent self-approval and self-promotion rejection;
- approval invalidation after material scope change;
- envelope tamper, schema, budget, and digest rejection;
- retry preserves prior envelopes and evidence;
- OpenAPI compatibility and disposable M4.5 demo twice.

### Needs revision when

- project direction or active behavior exists only in prompt text;
- a GoalRevision, AgentProfileVersion, ApprovedExecutionSpec, envelope, or
  evidence record can be edited in place;
- a planned or side-effecting Task can be unscoped;
- an API handler or graph node performs promotion or approval rules;
- an agent can approve its own proposal or promotion;
- a provider model name or CLI session identifier becomes a domain key;
- migration silently assigns historical unscoped Tasks to a Goal;
- M5 would require a domain or envelope redesign.

## Context compiler

### Accept when

- source scope and access rules are deterministic;
- every manifest has provenance, exclusions, token budget, and digest;
- provider-aware packing is enforced;
- retrieved instructions cannot change policy;
- deleted or revoked sources do not reappear.

### Required tests

- relevant selection;
- irrelevant exclusion;
- access denial;
- deduplication;
- hard token limit;
- stable digest;
- provider switch;
- poisoning content;
- deletion or revocation.

### Needs revision when

- full repository is sent by default;
- LLM ranking bypasses deterministic access rules;
- summaries have no provenance;
- token limit is soft or measured after the provider call.

## Agent Host and coding executor

### Accept when

- process lifecycle is observable and cancellable;
- workspace and environment are restricted;
- events and artifacts are normalized;
- timeout kills the full process tree;
- real OMP smoke test passes.

### Required tests

- start and successful result;
- ordered events;
- timeout;
- idempotent cancel;
- forbidden path;
- environment filtering;
- Agent Host restart;
- CLI version mismatch;
- real disposable-repository smoke.

### Needs revision when

- orphan processes remain;
- only fake process tests exist;
- terminal parsing has no version contract;
- output files can escape the workspace;
- executor IDs replace Jarvis IDs.

## Verifier

### Accept when

- deterministic gates decide mandatory success;
- reviewer model output is advisory and recorded;
- evidence is immutable;
- repair is bounded;
- failure produces actionable NEEDS_REVISION reasons.

### Required tests

- passing evidence;
- failing command;
- missing evidence;
- malicious test replacement;
- repair success within limit;
- repair exhaustion;
- reviewer disagreement.

### Needs revision when

- implementer self-approval is sufficient;
- a model can waive mandatory tests;
- repair has no limit;
- evidence can be edited after verification.

## Telemetry

### Accept when

- task, plan, run, model, and executor identifiers correlate;
- external calls emit duration and outcome;
- redaction is tested;
- OTel export is backend-neutral;
- telemetry failure does not corrupt domain behavior.

### Required tests

- connected end-to-end trace;
- error span;
- redaction fixtures;
- exporter outage;
- cost and usage normalization;
- no duplicate terminal metrics.

### Needs revision when

- logs cannot identify the task safely;
- secrets or private content are exported;
- observability requires LangSmith;
- telemetry exceptions fail the business transaction.

## Operator UI

### Accept when

- UI renders API state rather than inventing state;
- task list, plan, timeline, artifacts, and controls work;
- stale actions receive clear feedback;
- reconnect and refresh recover correctly;
- loading, empty, failure, and terminal states are represented.

### Required tests

- component tests for state variants;
- generated API client contract;
- approval, rejection, cancel, and retry;
- stale plan version;
- SSE reconnect;
- browser end-to-end planned task.

### Needs revision when

- UI reports success before API confirmation;
- refresh loses state;
- raw backend exceptions are shown;
- controls allow invalid transitions.

## Whole-system acceptance

The whole system is accepted only if:

- make verify passes from a clean checkout;
- M4.1 proves the real graph/API vertical path;
- the M4.5 controlled-direction demo and complete make demo pass twice
  consecutively;
- required M9 scenarios pass;
- all services expose useful health checks;
- no critical secret, dependency, or security finding is open;
- a reviewer can reproduce the evidence using repository documentation.

