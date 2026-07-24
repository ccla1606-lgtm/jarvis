# M4.5 operator direction and agent control

## 1. Purpose

M4.5 adds the minimum canonical control model required for one operator to direct
Jarvis over time before a real coding executor is connected in M5. It turns an
isolated Task into work that is traceable to a Project, an immutable Goal
revision, and an exact AgentProfile version. It also makes changes to agent
behavior proposal-driven, evidence-backed, explicitly approved, and reversible.

M4.5 is a control-plane milestone. It does not run autonomous agent teams, build
a scheduler, implement long-term semantic memory, or allow an agent to modify an
active profile or system policy directly.

## 2. Required baseline and actual starting state

Implementation starts from `main` after the merged M4 commit. The evidence audit
on 2026-07-24 establishes this baseline:

- M0 implementation and evidence accepted by PR #13;
- M1 implementation and evidence accepted by PR #14;
- M2 implementation merged by PR #15, while the two-provider credential-backed
  live smoke criterion remains externally blocked in issue #3;
- M3 implementation merged by PR #16, but the default API/demo composition does
  not yet prove the real graph path;
- M4 implementation merged by PR #17, but the full M3-to-M4 vertical path is not
  yet proven;
- M4.1 integration closure and M5+ runtime milestones are not implemented.

Therefore the implementation frontier is M4, while the integration frontier is
before M4.1. The release frontier is blocked by both the M2 live evidence and
the unproven M3-to-M4 integration. M4.1 must close the wiring gap before M4.5
contracts are implemented. M4.5 may proceed after M4.1 because the M2
credential blocker does not change its domain contracts, but neither M2 nor the
MVP release may be reported as fully accepted until the live smoke evidence is
attached.

## 3. Canonical hierarchy

The operator directs work through this hierarchy:

    Project
      -> Goal
        -> immutable GoalRevision
          -> Task
            -> immutable Plan version
              -> Approval
                -> ApprovedExecutionSpec
                  -> ExecutionEnvelope
                    -> Run

Agent behavior is selected through:

    AgentProfile
      -> immutable AgentProfileVersion
        -> ApprovedExecutionSpec

Behavior changes use:

    ChangeProposal
      -> immutable EvaluationEvidence records
        -> operator decision
          -> promotion or rollback

A system-development objective uses an ordinary Project with kind `SYSTEM`.
Jarvis must not introduce a second hidden hierarchy for its own development.

## 3.5 M4.1 prerequisite: prove the existing vertical path

M4.5 agents must not guess how M3 and M4 connect. Before M4.5-0, execute the M4.1 integration-closure gate:

1. wire the default API composition to the typed brain runtime;
2. send one fast read-only request through the deployed API and persist its terminal result;
3. send one complex side-effecting request and persist AWAITING_APPROVAL with exact Plan ID/version;
4. exercise approve, reject, cancel, retry, restart, and Last-Event-ID reconnect against the same PostgreSQL-backed application;
5. run the real demo twice and attach logs, transition IDs, and database checks;
6. record the current batch-and-reconnect SSE behavior as intentional, with long-held push deferred to the UI milestone.

M4.1 is not complete if the demo only checks RECEIVED, if create_app() uses a null brain on the accepted path, or if unit tests are the only evidence.

## 4. Non-negotiable invariants

1. PostgreSQL owns every canonical entity, version, transition, and digest.
2. A side-effecting or planned Task created after M4.5 must reference one active
   Goal and its current immutable GoalRevision.
3. The API may omit explicit scope only for a fast read-only request. The
   application resolves it to the versioned built-in Personal Project, Inbox
   GoalRevision, and assistant AgentProfileVersion; new canonical Tasks never
   store null direction or behavior.
4. A Goal revision never changes in place. Editing direction creates the next
   revision and does not alter already approved Tasks.
5. An AgentProfileVersion never changes in place after creation.
6. At most one AgentProfileVersion is ACTIVE for one AgentProfile.
7. Promotion, rollback, and all state-changing API commands are idempotent and
   use optimistic concurrency.
8. Approval binds the exact Project, GoalRevision, Plan version,
   AgentProfileVersion, repositories, tools, side-effect policy, budgets, and
   verification requirements into an immutable ApprovedExecutionSpec.
9. Dispatch receives an immutable ExecutionEnvelope whose digest covers every
   execution-affecting field. M5 must reject a digest mismatch.
10. A retry creates a new Run and a new envelope identifier. It never rewrites
    the prior envelope, run, evidence, or artifacts.
11. Expanding repositories, tools, side effects, budget ceilings, goal scope, or
    verification policy invalidates the prior approval.
12. Changing only provider resolution within an already approved logical model
    profile does not require a new approval, but the actual ModelResolution is
    recorded.
13. An agent may draft a ChangeProposal. Only the operator may approve promotion,
    application, rollback, goal completion, or a material scope expansion.
14. EvaluationEvidence is append-only, content-addressed, and cannot be replaced
    after an operator decision.
15. No API handler, graph node, provider adapter, or executor may bypass these
    application use cases.

## 5. Canonical contracts

### 5.1 Project

Required fields:

- `project_id`;
- `kind`: `WORK` or `SYSTEM`;
- `name`;
- `mission`;
- `status`: `ACTIVE`, `PAUSED`, or `ARCHIVED`;
- optimistic `version`;
- `created_at` and `updated_at`.

Rules:

- new Goals can be created only in an ACTIVE Project;
- PAUSED prevents new Task approval but preserves queries;
- ARCHIVED is terminal and preserves all history;
- Project mission edits use optimistic concurrency and are audited;
- an idempotent OperatorBootstrap use case creates the built-in Personal WORK
  Project, Inbox Goal, assistant profile, and initial immutable versions;
- built-in records obey ordinary versioning and audit rules and are not hidden
  configuration.

### 5.2 Goal and GoalRevision

`Goal` owns identity and lifecycle. `GoalRevision` owns immutable direction.

Goal fields:

- `goal_id`, `project_id`, optional `parent_goal_id`;
- `status`: `DRAFT`, `ACTIVE`, `PAUSED`, `ACHIEVED`, or `ABANDONED`;
- current revision number and optimistic version.

GoalRevision fields:

- `goal_id` and monotonically increasing `revision`;
- objective;
- one or more measurable success criteria;
- constraints and explicitly excluded scope;
- priority;
- time, token, and monetary ceilings where applicable;
- creation actor, reason, timestamp, and stable digest.

Rules:

- parent and child belong to the same Project;
- the hierarchy is acyclic;
- only an ACTIVE Goal can authorize a planned or side-effecting Task;
- ACHIEVED and ABANDONED are terminal;
- changing direction creates a revision and requires new approval for Tasks that
  have not started under the previous revision;
- goal completion requires operator action and at least one evidence reference.

### 5.3 AgentProfile and AgentProfileVersion

`AgentProfile` is a stable role identity. `AgentProfileVersion` is immutable
behavior configuration.

AgentProfile fields:

- `agent_profile_id`;
- unique `role_key` such as `architect`, `coder`, or `reviewer`;
- display name and purpose;
- status: `ACTIVE` or `ARCHIVED`;
- optimistic version.

AgentProfileVersion fields:

- monotonic version;
- status: `DRAFT`, `CANDIDATE`, `ACTIVE`, `RETIRED`, or `REJECTED`;
- instruction content or immutable artifact reference plus digest;
- logical model profile, never a raw provider model name;
- allowed tool classes and workspace policy;
- context policy and resource budgets;
- completion contract and verification policy;
- author, reason, timestamp, and stable digest.

Rules:

- DRAFT may become CANDIDATE or REJECTED;
- CANDIDATE may become ACTIVE or REJECTED;
- promoting a candidate retires the prior active version atomically;
- rollback activates an existing eligible prior version through a new audited
  promotion decision; it never edits history;
- a Run always references the exact version selected at approval.

### 5.4 ApprovedExecutionSpec

Created only by the application approval use case after validating all referenced
versions and scopes. Required fields:

- task, plan ID and plan version;
- project, goal ID and GoalRevision digest;
- AgentProfile and AgentProfileVersion digest;
- allowed repositories, workspaces, tools, and side-effect policy;
- maximum time, steps, tokens, monetary cost, and repair attempts;
- required verification commands and evidence types;
- approval ID, actor, timestamp, schema version, and canonical digest.

The canonical serialization algorithm and digest version are public contracts.
The serialized form contains no secrets.

### 5.5 ExecutionEnvelope

The envelope is the only start input accepted by CodingExecutorPort. It contains:

- envelope ID and schema version;
- ApprovedExecutionSpec ID and digest;
- task ID, run ID, and attempt number;
- exact AgentProfileVersion reference and digest;
- immutable context reference or explicit M5 fixture context digest;
- workspace root and repository revision;
- allowed tools and filtered environment key names;
- effective budgets bounded by the approved ceilings;
- verification contract;
- creation timestamp and envelope digest.

M4.5 implements the builder and deterministic validation. M5 consumes the
contract. M6 replaces explicit fixture context with a compiled ContextManifest
without changing the approved scope.

### 5.6 ChangeProposal and EvaluationEvidence

ChangeProposal fields:

- proposal ID;
- target kind and exact target version;
- proposed replacement version or code Task reference;
- rationale, expected benefit, known risks, and rollback target;
- status: `DRAFT`, `EVALUATING`, `AWAITING_APPROVAL`, `APPROVED`, `REJECTED`,
  `APPLIED`, or `ROLLED_BACK`;
- operator decision metadata and optimistic version.

EvaluationEvidence fields:

- evidence ID and proposal ID;
- benchmark or scenario identifier;
- baseline and candidate references;
- normalized quality, latency, token, and cost measurements;
- command, artifact reference, digest, timestamp, and producer;
- pass/fail result against declared thresholds.

M4.5 records deterministic or manually initiated evidence. M7 adds automated
verification and evaluation execution. Missing evidence can never be interpreted
as improvement.

## 6. API changes

All state-changing commands require authentication, an idempotency key, expected
resource version, and a stable error envelope.

Minimum endpoints:

- `POST /v1/projects`, `GET /v1/projects`, `GET /v1/projects/{project_id}`;
- `PATCH /v1/projects/{project_id}` and explicit pause/archive commands;
- `POST /v1/projects/{project_id}/goals`;
- `GET /v1/goals/{goal_id}` and `POST /v1/goals/{goal_id}/revisions`;
- explicit activate, pause, achieve, and abandon Goal commands;
- `POST /v1/agent-profiles`, `GET /v1/agent-profiles`;
- `POST /v1/agent-profiles/{profile_id}/versions`;
- explicit candidate, promote, reject, and rollback commands;
- `POST /v1/change-proposals` and evidence append/query endpoints;
- explicit submit-for-approval, approve, reject, apply, and rollback commands;
- task submission fields for project, goal, goal revision, and agent profile;
- task detail projections exposing all bound versions and digests.

Do not implement a generic endpoint that accepts an arbitrary target state.
Commands name the business action and application code validates the transition.

## 7. Ordered implementation work packages

Each package is a separate issue or a separately reviewable commit. Agents must
not start package N+1 until package N has the listed exit evidence.

### M4.5-0: baseline and contract freeze

Actions:

1. verify that M4.1 is INTEGRATION-ACCEPTED and attach its evidence packet;
2. fetch `main`, verify M4 commit and CI evidence;
2. record the M2 live-smoke blocker without claiming it passed;
3. inventory current Task, Plan, Approval, Run, repository, API, and graph
   contracts;
4. write the schema and transition tables from this specification as tests or
   fixtures before production code;
5. identify exact existing call sites that create an Approval or Run.

Exit evidence:

- no production code change;
- contract inventory is attached to the issue;
- every new entity and transition has a named owner module;
- open questions that change persistence or API contracts are resolved by the
  operator.

### M4.5-1: pure domain model

Owned modules: `domain` and unit tests only.

Actions:

1. add typed IDs, enums, value objects, entities, and errors;
2. implement Project, Goal, and AgentProfile transition functions;
3. implement immutable revision/version constructors;
4. implement hierarchy cycle validation and material-scope comparison;
5. implement canonical serialization and versioned digest helpers;
6. prohibit framework, database, HTTP, provider, graph, and CLI imports.

Exit evidence:

- exhaustive allowed and forbidden transition tests;
- invalid construction, cycle, stale version, and digest tests;
- deterministic serialization golden vectors;
- domain tests pass twice with no network, subprocess, or database.

### M4.5-2: PostgreSQL persistence and migrations

Owned modules: repository ports, PostgreSQL adapters, migrations, integration
tests. Do not add API routes or graph behavior.

Actions:

1. create append-preserving tables, indexes, foreign keys, and uniqueness rules;
2. keep historical M0-M4 Tasks queryable; historical unscoped Tasks remain
   explicitly `legacy_unscoped` and are never silently assigned a Goal;
3. implement repositories and transaction boundaries;
4. enforce one ACTIVE profile version atomically;
5. enforce idempotency and optimistic concurrency with real PostgreSQL;
6. document forward migration and rollback limitations.

Exit evidence:

- migration from the current M4 schema succeeds;
- migration from empty succeeds;
- OperatorBootstrap is idempotent under concurrent startup and creates exactly
  one Personal/Inbox/default-profile set;
- restart and re-read preserve every digest and transition;
- concurrent promotion has one winner and one classified conflict;
- rollback leaves no partial rows;
- repository contract suite passes against real PostgreSQL.

### M4.5-3: application use cases

Owned modules: application services and deterministic tests. Do not add direct
HTTP or LangGraph decisions.

Actions:

1. implement Project and Goal commands and queries;
2. implement profile version drafting, candidacy, promotion, rejection, and
   rollback;
3. implement proposal and evidence commands;
4. require explicit active Goal scope for new planned or side-effecting Tasks;
5. resolve omitted fast read-only scope through OperatorBootstrap defaults and
   persist the resolved versions;
6. implement ApprovedExecutionSpec creation and approval invalidation;
7. keep all commands transactional and idempotent.

Exit evidence:

- use-case tests cover happy path, stale version, invalid transition, duplicate
  command, archived project, paused goal, scope expansion, and rollback;
- no handler or graph dependency exists;
- approval of a changed GoalRevision or profile version fails safely.

### M4.5-4: execution contract integration

Owned modules: application contracts, executor port contract, graph translation,
and contract tests. Do not start OMP or another real CLI.

Actions:

1. change approval to create an ApprovedExecutionSpec;
2. implement the deterministic ExecutionEnvelope builder;
3. make CodingExecutorPort accept only an ExecutionEnvelope;
4. use a fake/recording executor to prove the exact envelope handed to dispatch;
5. ensure retry creates a new envelope and preserves prior attempts;
6. reject missing, altered, unsupported-schema, or over-budget envelopes.

Exit evidence:

- contract tests prove stable digests and tamper rejection;
- existing M3/M4 fast and approval paths remain green;
- no real subprocess is started;
- M5 can implement an adapter without changing domain entities or the envelope.

### M4.5-5: versioned API and projections

Owned modules: FastAPI schemas/handlers, OpenAPI artifact, web API types/fixtures,
and API tests. Handlers call application use cases only.

Actions:

1. add the minimum endpoints listed above;
2. add stable error codes and correlation identifiers;
3. extend task submission and detail projections;
4. regenerate and review OpenAPI;
5. add resumable events for goal, profile, proposal, and promotion transitions;
6. prove restart reconstruction from PostgreSQL.

Exit evidence:

- OpenAPI freshness and compatibility tests pass;
- command idempotency and stale-version tests use the real API boundary;
- API restart preserves active Goals and profile versions;
- UI fixtures parse with both Pydantic and TypeScript.

### M4.5-6: controlled evolution workflow

Owned modules: application workflow, persistence, API, and deterministic
evaluation fixtures. Do not implement automatic self-modification.

Actions:

1. create a candidate profile version only through an explicit command;
2. create a ChangeProposal referencing candidate and baseline;
3. append immutable evaluation evidence;
4. calculate deterministic threshold results;
5. require operator approval before promotion or application;
6. implement audited rollback to an eligible prior profile version;
7. prove that an agent-originated proposal cannot approve itself.

Exit evidence:

- missing or failing evidence blocks promotion;
- repeated approval/application/rollback is idempotent;
- the active version changes atomically;
- old Runs retain their original profile version;
- every decision is queryable with actor, reason, evidence, and digest.

### M4.5-7: demo, documentation, and milestone evidence

Actions:

1. extend `make demo` with a disposable SYSTEM Project, active Goal, coder profile,
   candidate version, evidence, promotion, scoped Task, approval spec, and
   recording-executor envelope;
2. run the demo twice and prove one canonical result for repeated commands;
3. update architecture, API, domain, migration, and operator documentation;
4. run the complete deterministic `make verify` gate;
5. attach an evidence packet and list the still-open M2 live blocker.

Exit evidence:

- all M4.5 acceptance criteria pass;
- `make verify` and the extended `make demo` pass twice;
- no active-path stub or skipped mandatory deterministic test exists;
- current status documentation distinguishes implementation frontier from release
  acceptance;
- M5 issue and roadmap depend on M4.5.

## 8. M4.5 milestone acceptance and transition to M5

M4.5 is IMPLEMENTED only when all work packages are complete. It is accepted for
M5 handoff only when:

1. Project, GoalRevision, AgentProfileVersion, ApprovedExecutionSpec,
   ExecutionEnvelope, ChangeProposal, and EvaluationEvidence are durable;
2. all versioned transitions, idempotency, concurrency, migration, restart, and
   tamper tests pass;
3. a planned side-effecting Task cannot be approved without explicit active
   Goal scope and an eligible AgentProfileVersion;
4. an omitted fast read-only scope resolves to persisted built-in versions;
5. the exact approved scope can be reconstructed after process restart;
6. a recording executor receives the expected envelope and rejects mutation;
7. controlled promotion and rollback preserve historical Runs;
8. OpenAPI, web fixtures, documentation, `make verify`, and `make demo` agree;
9. the evidence packet contains commands, results, migration version, known
   limitations, and remaining release blockers.

M5 may start when M4.5 is implemented and its deterministic evidence is complete.
The isolated M2 credential blocker may remain open only if the operator records
that it does not affect M5 executor contracts. M5 must not be declared release-
accepted, and M9 cannot close, until the M2 live smoke passes.

## 9. Explicitly deferred

The following remain post-MVP unless a new accepted ADR changes the plan:

- autonomous goal decomposition and scheduling;
- permanent multi-agent teams;
- agents promoting their own versions;
- self-editing active prompts, policies, tools, or source code;
- unrestricted recursive delegation;
- semantic long-term memory or knowledge graph;
- automated production deployment;
- multi-user RBAC, enterprise identity, or billing;
- advanced VM or kernel sandboxing.
