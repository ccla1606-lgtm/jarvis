# Jarvis MVP architecture

## 1. Architectural goal

Build a single-operator assistant that preserves long-term system direction,
answers simple requests quickly, plans complex work, binds execution to
measurable Goals and versioned AgentProfiles, obtains human approval, executes
bounded coding tasks through replaceable CLI agents, and exposes durable state,
evidence, and traces through an operator UI.

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
8. Direction, agent behavior, approval scope, and evaluation evidence are
   versioned domain state rather than mutable prompt text.
9. Agents may propose evolution; only the operator promotes or rolls it back.

## 3. MVP boundaries

### Included

- single-operator WORK and SYSTEM Projects with measurable versioned Goals;
- versioned AgentProfiles and controlled promotion or rollback;
- immutable approved execution specifications and dispatch envelopes;
- evidence-backed ChangeProposals for agent and system evolution;
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

- Project: operator-owned WORK or SYSTEM direction boundary.
- Goal and GoalRevision: lifecycle plus immutable measurable direction.
- AgentProfile and AgentProfileVersion: stable role plus immutable behavior.
- ApprovedExecutionSpec: exact scope and policy authorized by one Approval.
- ExecutionEnvelope: content-addressed package accepted by an executor.
- ChangeProposal and EvaluationEvidence: controlled, reversible evolution.
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

- create, revise, pause, achieve, abandon, and query Projects and Goals;
- create, evaluate, promote, retire, roll back, and query agent profiles;
- create and decide ChangeProposals and append immutable evidence;
- build and validate ApprovedExecutionSpec and ExecutionEnvelope;
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

1. resolve the ApprovedExecutionSpec, GoalRevision, AgentProfileVersion, task
   scope, and allowed repositories;
2. load explicitly referenced artifacts;
3. retrieve candidate files or records;
4. filter by access, trust, and relevance;
5. rank and deduplicate;
6. fit provider-aware token budget;
7. emit immutable ContextManifest.

MVP memory consists of task history, approved summaries, and referenced
artifacts. It is not an autonomous agent.

### executors

Owns CodingExecutorPort and adapters. CodingExecutorPort accepts only a
validated immutable ExecutionEnvelope. The first adapter starts an OMP session
in an isolated Agent Host process. Later adapters may support Codex CLI, Claude
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

## 6. Operator direction and agent control

Canonical hierarchy:

    Project
      -> Goal
        -> immutable GoalRevision
          -> Task
            -> immutable Plan version
              -> Approval
                -> ApprovedExecutionSpec
                  -> ExecutionEnvelope
                    -> Run

Agent behavior is selected through immutable AgentProfileVersion. System
development is an ordinary Project with kind SYSTEM; it does not use hidden
system prompts as canonical direction.

A planned or side-effecting Task must bind an active GoalRevision before approval.
Approval snapshots every material execution field. A material change to goal
scope, repositories, tools, side effects, budgets, verification policy, or agent
behavior invalidates the approval. Provider resolution inside the approved logical
model profile is recorded but does not expand scope.

An agent can create a ChangeProposal and attach evidence. Promotion, application,
rollback, and Goal completion require an explicit operator command. Full
contracts and ordered implementation packages are in
[M4.5 execution specification](M4_5_EXECUTION_SPEC.md).

## 7. Canonical task state machine

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

## 8. Core ports

### ModelPort

Responsibilities:

- invoke a logical model profile;
- return normalized content, tool calls, structured data, usage, and resolution;
- support cancellation and timeout;
- classify provider errors.

### TaskRepository

Responsibilities:

- transactionally create and update Projects, Goals, profile versions,
  proposals, tasks, plans, runs, approvals, specs, and envelopes;
- enforce optimistic concurrency;
- expose append-only transition history;
- support idempotency keys.

### DirectionRepository

Responsibilities:

- transactionally persist Projects, Goal revisions, AgentProfile versions,
  ChangeProposals, evidence, ApprovedExecutionSpecs, and ExecutionEnvelopes;
- enforce append-only versions, optimistic concurrency, idempotency, and one
  active profile version;
- reconstruct exact approved scope after restart.

### ExecutionSpecBuilder

Responsibilities:

- validate Project, Goal, Plan, profile, policy, and budget versions;
- create canonical ApprovedExecutionSpec and ExecutionEnvelope payloads;
- calculate versioned stable digests;
- reject tampering, stale scope, and unsupported schemas.

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

## 9. Persistence

PostgreSQL is canonical for:

- Projects, Goals, and immutable Goal revisions;
- AgentProfiles and immutable AgentProfile versions;
- ChangeProposals and immutable EvaluationEvidence;
- ApprovedExecutionSpecs and ExecutionEnvelopes;
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

## 10. API boundary

Initial task endpoints:

- POST /v1/tasks
- GET /v1/tasks
- GET /v1/tasks/{task_id}
- POST /v1/tasks/{task_id}/approve
- POST /v1/tasks/{task_id}/reject
- POST /v1/tasks/{task_id}/cancel
- POST /v1/tasks/{task_id}/retry
- GET /v1/tasks/{task_id}/events
- project and explicit Goal lifecycle command/query endpoints;
- agent-profile version, candidate, promotion, rejection, and rollback endpoints;
- ChangeProposal, evidence, decision, application, and rollback endpoints;
- GET /health/live
- GET /health/ready

Commands accept an idempotency key. API schemas are versioned and generated
from canonical Pydantic models. The UI consumes the same OpenAPI contract.

## 11. Security baseline

- secrets come from environment or a secret provider, never source control;
- configuration startup fails on missing required secrets;
- subprocesses receive a minimal environment;
- workspace paths are allowlisted;
- dangerous tool actions and material scope expansion require approval;
- active agent profiles cannot approve or mutate their own versions;
- every executor start validates approved-spec and envelope digests;
- stdout, stderr, prompts, and traces pass through redaction;
- external content is untrusted and cannot change system policy;
- all external calls use explicit timeouts;
- cancellation and process termination are tested;
- the Agent Host cannot access unrelated workspaces.

## 12. Replaceability requirements

The architecture is portable only if these tests remain true:

1. the graph can run directly without LangGraph Agent Server;
2. the same application test suite passes with fake, GPT-family, and
   DeepSeek-family model adapters;
3. adding a second coding CLI does not modify domain entities;
4. disabling LangSmith does not remove canonical traces or task history;
5. UI state can be rebuilt from API and task events;
6. no provider-specific identifier is used as a Jarvis primary key;
7. a second coding CLI consumes the same ExecutionEnvelope;
8. historical Runs remain reproducible after profile promotion or rollback;
9. system direction can be reconstructed from Project and Goal revisions without
   reading hidden prompts.

## 13. Deployment shape

MVP Docker Compose services:

- api;
- web;
- agent-host;
- postgres;
- otel-collector;
- optional local LangGraph development server.

Redis, queues, and additional workers are introduced only after measured
concurrency or reliability requirements justify them.
