# Architecture decisions

## ADR-001: Modular monolith control plane

Status: accepted for MVP.

The API, application services, domain, LangGraph graph, model gateway, context
compiler, and telemetry integration live in one Python deployable. Agent Host
runs separately for process isolation.

Reason: this minimizes distributed failure modes and is easier for a coding
agent to assemble and verify.

## ADR-002: LangGraph is the workflow brain

Status: accepted for MVP.

LangGraph Core implements routing, planning, approval interrupt, dispatch,
verification, and final synthesis.

The graph must also run directly in tests and local runtime. LangGraph Agent
Server and LangSmith Studio are optional acceleration and debugging surfaces,
not domain dependencies.

## ADR-003: PostgreSQL owns canonical state

Status: accepted.

Task, plan, approval, run, transition, artifact metadata, model resolution, and
trace references are stored in Jarvis tables. LangGraph checkpoints, LangSmith
threads, terminal sessions, and UI caches are projections.

## ADR-004: Provider-independent model profiles

Status: accepted.

Application code requests a logical profile. The model layer resolves provider,
model, account, capabilities, and fallback. GPT-family and DeepSeek-family
adapters must pass one contract suite.

LiteLLM may implement common gateway behavior, but provider-native adapters are
allowed when a required capability cannot be represented safely.

## ADR-005: Coding CLIs are adapters

Status: accepted.

CodingExecutorPort owns the domain contract. OMP is the first adapter. Codex
CLI, Claude Code, OpenCode, and other agents may be added without changing
domain entities.

Stable RPC, SDK, or agent protocol integration is preferred. PTY parsing is a
versioned fallback.

## ADR-006: Deterministic Context Compiler

Status: accepted for MVP.

Context selection, access filtering, packing, and token budgets are controlled
by deterministic code. Models may rank or summarize candidates but cannot
change policy or task scope.

MVP memory contains durable task history, approved summaries, and explicit
artifact references. There is no autonomous memory agent.

## ADR-007: OpenTelemetry is canonical

Status: accepted.

All modules emit OpenTelemetry-compatible spans, metrics, and correlated logs.
LangSmith may receive traces during development, but disabling it must not
remove task history or baseline observability.

## ADR-008: Human approval binds immutable scope

Status: accepted.

Approval references an immutable plan version and allowed scope. Any material
change to repositories, tools, side effects, cost, or plan steps requires a new
plan version and approval.

## ADR-009: Production-shaped, not production-complete

Status: accepted for MVP.

The MVP includes typed contracts, migrations, timeouts, retries, cancellation,
idempotency, tests, traces, and security boundaries.

It explicitly excludes Temporal, Kubernetes, multi-region, autonomous teams,
Knowledge Plane, self-improvement, and advanced sandbox infrastructure until
measured requirements justify them.

## ADR-010: Single-operator product boundary

Status: accepted for MVP.

Jarvis serves one authenticated operator. WORK and SYSTEM Projects share one
domain model. Multi-user RBAC, organization tenancy, billing, and enterprise
identity remain post-MVP. The single-user boundary does not remove
authentication, audit history, idempotency, workspace isolation, or secret
handling.

## ADR-011: Durable Project and immutable Goal revisions

Status: accepted for M4.5.

Long-term direction is represented by Project, Goal, and immutable GoalRevision
records in PostgreSQL. Planned or side-effecting Tasks bind an active revision.
Changing direction never rewrites already approved or completed work. Jarvis
system development uses a Project with kind SYSTEM rather than a privileged
hidden planning mechanism.

## ADR-012: Versioned agents and content-addressed execution

Status: accepted for M4.5.

AgentProfile is stable role identity; AgentProfileVersion is immutable behavior.
Approval creates an ApprovedExecutionSpec that binds goal, plan, profile, scope,
tools, side effects, budgets, and verification. CodingExecutorPort accepts only
an immutable ExecutionEnvelope derived from that spec. Every version and envelope
uses canonical serialization with a schema-versioned digest.

## ADR-013: Proposal-driven evolution with operator promotion

Status: accepted for M4.5.

Agents may draft ChangeProposals and evaluation evidence. They cannot mutate,
promote, apply, or roll back active profiles or policies. Promotion and rollback
are explicit operator commands, preserve history, and require reproducible
evidence. M4.5 records deterministic evidence; M7 adds automated evaluation and
verification execution.

## ADR-014: Separate implementation, integration, and release evidence

Status: accepted.

A milestone can have implemented code while its real module path is not yet
wired, or while mandatory live evidence is externally blocked. Downstream
implementation may proceed only when the operator records why the blocker cannot
invalidate downstream contracts. Release acceptance remains blocked, and no
missing integration or live evidence may be described as passed.

## Decision change procedure

A change requires:

1. a new or amended ADR;
2. impact on contracts, persistence, tests, deployment, and migration;
3. explicit human acceptance;
4. updates to affected implementation issues.

Coding agents must not silently replace an accepted decision.

