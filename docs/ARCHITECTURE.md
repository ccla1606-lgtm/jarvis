# Jarvis MVP architecture

## 1. Architectural goal

Build an assistant that can answer simple requests quickly, plan complex work,
obtain human approval, execute bounded coding tasks through replaceable CLI
agents, and expose durable task state and traces through an operator UI.

The architecture must be easy for a coding agent to implement and verify.
Therefore the control plane begins as a modular monolith, while coding execution
runs in isolated worker processes.

## 2. Principles

1. Domain state belongs to Jarvis.
2. LLMs propose decisions; deterministic code validates and enforces them.
3. Every external technology sits behind a typed port.
4. One vertical slice is preferred over many incomplete subsystems.
5. Observability and cancellation are features, not later additions.
6. Provider portability is tested, not assumed.
7. Production-shaped means clean boundaries and evidence, not enterprise scale.

## 3. MVP boundaries

### Included

- user request intake;
- fast, bounded, and planned routing;
- typed plan creation;
- approval, rejection, cancellation, retry, and resume;
- GPT-family and DeepSeek-family provider adapters;
- one working coding CLI adapter, with OMP as the first target;
- deterministic context compilation;
- PostgreSQL persistence;
- OpenTelemetry traces and correlated logs;
- operator UI with task list, task detail, plan, run state, artifacts, and traces;
- reproducible Docker Compose environment;
- deterministic CI and a separate live smoke lane.

### Excluded until after MVP

- Temporal or another second workflow engine;
- Kubernetes and multi-region deployment;
- autonomous permanent agent teams;
- unrestricted recursive subagents;
- Knowledge Plane or knowledge graph;
- autonomous memory agent;
- self-modifying prompts or policies;
- OPA/Rego unless simple policy code proves insufficient;
- gVisor, Kata, and advanced sandbox backends;
- automatic production deployment;
- multi-tenant billing and enterprise identity.

## 4. System topology

    User
      |
      v
    Web UI ---- REST/SSE ---- FastAPI
                              |
                    Application services
                              |
              +---------------+----------------+
              |               |                |
          LangGraph       PostgreSQL       OpenTelemetry
              |                                 |
        typed ports                       OTel Collector
        /     |      \
    Models  Context  CodingExecutor
      |       |          |
    Gateway  Store    Agent Host process
      |                  |
    GPT / DeepSeek      OMP CLI

LangSmith Studio may connect to the LangGraph development runtime. LangSmith
run and thread identifiers are external references, never canonical task IDs.

## 5. Modules and ownership

### domain

Owns immutable identifiers, entities, value objects, state transitions, and
error categories.

Primary entities:

- Task: user intent and canonical lifecycle.
- Plan: versioned proposed steps and approval state.
- Run: one execution attempt.
- Approval: explicit decision with actor and timestamp.
- Artifact: immutable reference to produced evidence.
- ModelResolution: actual provider/model/account selected for a call.
- TraceLink: mapping from Jarvis IDs to telemetry backends.

Domain code is pure Python and has no framework or infrastructure imports.

### application

Owns use cases and transaction boundaries:

- submit request;
- classify request;
- create and revise plan;
- approve or reject plan;
- start, cancel, resume, and retry run;
- collect artifacts;
- verify result;
- query task status.

### graph

Owns LangGraph graph construction and state translation. Nodes call application
ports; they do not call provider SDKs or subprocesses directly.

Initial nodes:

- intake;
- triage;
- fast_answer;
- bounded_task;
- create_plan;
- wait_for_approval;
- dispatch;
- verify;
- synthesize;
- finalize.

### models

Owns ModelPort, logical profiles, provider capability matrix, routing,
timeouts, retry classification, usage normalization, and adapters.

Initial logical profiles:

- fast: low latency, low cost;
- planner: strong structured reasoning;
- coder: coding quality and tool use;
- reviewer: independent verification;
- summarizer: bounded compression.

### context

Owns deterministic context selection and packing:

1. resolve task scope and allowed repositories;
2. load explicitly referenced artifacts;
3. retrieve candidate files or records;
4. filter by access, trust, and relevance;
5. rank and deduplicate;
6. fit provider-aware token budget;
7. emit immutable ContextManifest.

MVP memory consists of task history, approved summaries, and referenced
artifacts. It is not an autonomous agent.

### executors

Owns CodingExecutorPort and adapters. The first adapter starts an OMP session in
an isolated Agent Host process. Later adapters may support Codex CLI, Claude
Code, OpenCode, or another protocol-compatible agent.

The executor must support:

- start;
- stream events;
- inspect status;
- cancel;
- collect result and artifacts;
- enforce timeout and resource budget.

### telemetry

Owns trace names, span attributes, correlation identifiers, redaction, metrics,
and log structure. OpenTelemetry is canonical; backend exporters are replaceable.

### infrastructure

Owns PostgreSQL repositories, migrations, transaction handling, process
management, filesystem artifact storage, and configuration loading.

## 6. Canonical task state machine

Allowed states:

    RECEIVED
      -> TRIAGING
      -> ANSWERING
      -> PLANNING
      -> AWAITING_APPROVAL
      -> QUEUED
      -> RUNNING
      -> VERIFYING
      -> SUCCEEDED

Terminal or exceptional states:

    REJECTED
    CANCELLED
    FAILED
    NEEDS_REVISION

Rules:

- only declared transitions are accepted;
- every transition is stored with task ID, attempt ID, actor, reason, and time;
- approval applies to one immutable plan version;
- retry creates a new Run and does not rewrite prior evidence;
- cancellation is idempotent;
- a process restart must not lose an accepted transition.

## 7. Core ports

### ModelPort

Responsibilities:

- invoke a logical model profile;
- return normalized content, tool calls, structured data, usage, and resolution;
- support cancellation and timeout;
- classify provider errors.

### TaskRepository

Responsibilities:

- transactionally create and update tasks, plans, runs, and approvals;
- enforce optimistic concurrency;
- expose append-only transition history;
- support idempotency keys.

### ContextCompilerPort

Responsibilities:

- compile a ContextManifest from explicit task scope and policy;
- report selected and excluded sources;
- enforce a hard token budget;
- produce a stable digest for the same inputs.

### CodingExecutorPort

Responsibilities:

- start a bounded coding task;
- stream normalized events;
- cancel and inspect a run;
- return immutable result and artifact references.

### TelemetryPort

Responsibilities:

- start correlated spans;
- record normalized metrics and safe events;
- redact secrets before export.

## 8. Persistence

PostgreSQL is canonical for:

- tasks and transitions;
- plans and versions;
- approvals;
- runs and attempts;
- idempotency records;
- artifact metadata;
- model resolutions;
- external trace references.

Large logs and artifacts may use local object-style storage in MVP. PostgreSQL
stores immutable references and digests.

LangGraph checkpoints may use PostgreSQL, but checkpoint tables are not a
replacement for domain tables.

## 9. API boundary

Initial endpoints:

- POST /v1/tasks
- GET /v1/tasks
- GET /v1/tasks/{task_id}
- POST /v1/tasks/{task_id}/approve
- POST /v1/tasks/{task_id}/reject
- POST /v1/tasks/{task_id}/cancel
- POST /v1/tasks/{task_id}/retry
- GET /v1/tasks/{task_id}/events
- GET /health/live
- GET /health/ready

Commands accept an idempotency key. API schemas are versioned and generated
from canonical Pydantic models. The UI consumes the same OpenAPI contract.

## 10. Security baseline

- secrets come from environment or a secret provider, never source control;
- configuration startup fails on missing required secrets;
- subprocesses receive a minimal environment;
- workspace paths are allowlisted;
- dangerous tool actions require approval;
- stdout, stderr, prompts, and traces pass through redaction;
- external content is untrusted and cannot change system policy;
- all external calls use explicit timeouts;
- cancellation and process termination are tested;
- the Agent Host cannot access unrelated workspaces.

## 11. Replaceability requirements

The architecture is portable only if these tests remain true:

1. the graph can run directly without LangGraph Agent Server;
2. the same application test suite passes with fake, GPT-family, and
   DeepSeek-family model adapters;
3. adding a second coding CLI does not modify domain entities;
4. disabling LangSmith does not remove canonical traces or task history;
5. UI state can be rebuilt from API and task events;
6. no provider-specific identifier is used as a Jarvis primary key.

## 12. Deployment shape

MVP Docker Compose services:

- api;
- web;
- agent-host;
- postgres;
- otel-collector;
- optional local LangGraph development server.

Redis, queues, and additional workers are introduced only after measured
concurrency or reliability requirements justify them.
