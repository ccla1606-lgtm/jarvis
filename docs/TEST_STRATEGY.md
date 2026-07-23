# Test strategy

## 1. Goals

Tests must prove behavioral correctness, provider portability, durable state,
bounded execution, safe cancellation, and reproducible assembly by a coding
agent.

The default test suite is deterministic and does not require paid APIs.
Credential-backed compatibility is proven in a separate live smoke lane.

## 2. Test layers

### Unit

Scope:

- pure domain rules;
- state transitions;
- routing validators;
- budget calculations;
- error classification;
- context ranking and packing;
- redaction;
- configuration parsing.

Rules:

- no network;
- no subprocess;
- no real database;
- fast and deterministic.

### Contract

Scope:

- ModelPort adapters;
- TaskRepository implementations;
- CodingExecutor adapters;
- ContextCompiler;
- API error envelope;
- event schemas.

The same contract suite runs against every implementation. A fake adapter is
useful for development but cannot replace a required real implementation.

### Integration

Scope:

- PostgreSQL transactions and migrations;
- LangGraph checkpoint and resume;
- API plus PostgreSQL;
- OTel Collector export;
- Agent Host process lifecycle;
- filesystem artifact store;
- UI generated client against API schema.

Integration tests use real local dependencies through containers.

### End-to-end

Scope:

- browser or API request through complete backend;
- plan approval;
- executor dispatch;
- verification;
- UI timeline and artifacts;
- cancellation and retry;
- restart recovery.

The deterministic E2E lane uses fake LLM and fixture executor implementations,
but real API, graph, PostgreSQL, telemetry, and UI.

### Live smoke

Scope:

- one GPT-family provider;
- one DeepSeek-family provider;
- one real OMP coding run;
- optional LangSmith trace export.

Live smoke tests:

- are never hidden inside unit or default integration tests;
- require explicit credentials;
- record provider, model, timestamp, and sanitized evidence;
- have conservative cost and time limits;
- fail release promotion when required, but do not make every pull request
  depend on third-party availability.

## 3. Pull-request gates

make verify must run:

1. formatting check;
2. Python lint;
3. Python static typing;
4. TypeScript lint and type check;
5. unit tests with coverage report;
6. contract tests using deterministic adapters;
7. PostgreSQL integration tests;
8. API schema compatibility;
9. deterministic E2E smoke;
10. secret scan;
11. dependency vulnerability scan at the configured severity.

No gate may be converted to allow-failure without an accepted decision.

## 4. Required scenario matrix

### Request routing

- simple request -> fast answer -> SUCCEEDED;
- complex request -> plan -> AWAITING_APPROVAL;
- malformed classifier output -> bounded repair or classified failure;
- budget exceeded -> FAILED without further model calls.

### Approval

- correct plan version -> execution allowed;
- stale plan version -> conflict;
- rejection -> REJECTED and no executor run;
- duplicate approval -> idempotent result;
- restart while waiting -> approval still possible.

### Models

- primary success;
- primary timeout -> allowed fallback;
- 401 -> no blind retry;
- 429 -> bounded backoff;
- 5xx -> classified retry;
- context overflow -> recompile or fail safely;
- invalid structured output -> bounded repair;
- cancellation during stream;
- unsupported capability -> explicit failure.

### Persistence

- duplicate create command;
- concurrent update;
- transaction rollback;
- migration from empty;
- process restart;
- prior attempts remain queryable;
- artifact digest mismatch is rejected.

### Context

- explicit reference included;
- irrelevant source excluded;
- forbidden source denied;
- duplicated source deduplicated;
- hard token limit;
- stable digest;
- prompt injection in retrieved content;
- revoked content excluded.

### Executor

- successful fixture edit;
- ordered event stream;
- timeout;
- user cancel;
- process tree termination;
- forbidden filesystem path;
- missing CLI binary;
- unsupported CLI version;
- Agent Host restart;
- immutable artifacts.

### Verification

- all mandatory commands pass;
- one mandatory command fails;
- required evidence missing;
- implementing agent claims success while checks fail;
- bounded repair succeeds;
- repair budget exhausted.

### UI

- loading and empty task list;
- fast-answer task;
- awaiting approval;
- running timeline;
- failed and needs-revision state;
- approval conflict;
- cancel and retry;
- SSE disconnect and reconnect;
- refresh during active run;
- trace and artifact links.

### Observability

- successful connected trace;
- provider error trace;
- executor cancellation trace;
- redaction;
- exporter unavailable;
- usage and cost aggregation;
- no duplicate terminal metric.

## 5. Rework policy

An issue automatically returns to NEEDS_REVISION when:

- a mandatory test fails;
- a required test is skipped without an accepted blocker;
- the test is flaky in two runs;
- make verify or required make demo fails;
- the implementation passes only with network or credentials in the default lane;
- evidence cannot be reproduced;
- behavior differs from the issue acceptance contract;
- security or architecture invariants are violated;
- active-path stubs or fake success remain.

An issue is BLOCKED rather than failed when:

- required third-party credentials are unavailable;
- a provider outage prevents only the live lane;
- an unresolved human decision materially changes the implementation;
- the test environment lacks a declared required capability.

Blocked issues must include the exact unblock action and must not be reported as
complete.

## 6. Flaky-test rule

A retry may be used to investigate infrastructure behavior, but not to make a
flaky test green. The owner must:

1. reproduce the failure;
2. classify nondeterminism;
3. remove time, ordering, shared-state, network, or race dependency;
4. run the repaired test repeatedly;
5. record the root cause.

## 7. Test data

- fixtures contain no real secrets or personal data;
- deterministic provider responses are versioned;
- disposable repositories are created for executor tests;
- clocks and random identifiers are injectable;
- large artifacts are generated during tests, not committed;
- golden snapshots are used only for stable contracts, not broad UI markup.

## 8. Release evidence

The release evidence packet contains:

- commit SHA;
- dependency lock digests;
- database migration version;
- make verify output;
- make demo output;
- live provider smoke results;
- OMP smoke result;
- security scan result;
- backup/restore evidence;
- known limitations.

