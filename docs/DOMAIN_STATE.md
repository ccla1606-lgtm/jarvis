# Domain state and PostgreSQL persistence

## Boundary

M1 gives Jarvis ownership of canonical workflow state. Domain modules import no
FastAPI, LangGraph, provider SDK, or PostgreSQL code. Application services depend
only on `TaskRepository`; PostgreSQL and the in-memory unit-test adapter implement
that port.

The canonical entities are:

- `Task`: user objective, lifecycle, and optimistic version;
- `TaskTransition`: immutable evidence for one accepted lifecycle edge;
- `Plan`: immutable numbered steps and version;
- `Approval`: explicit actor decision bound to one plan ID and version;
- `Run`: one execution attempt with a link to the previous attempt;
- `Artifact`, `ModelResolution`, and `TraceLink`: immutable evidence metadata.

Identifiers are typed UUID values. Timestamps are timezone-aware UTC values.
Provider payloads, graph checkpoints, terminal sessions, and UI caches are not
canonical state.

## Task state machine

The declared edges are:

| From | Allowed targets |
|---|---|
| `RECEIVED` | `TRIAGING`, `CANCELLED`, `FAILED` |
| `TRIAGING` | `ANSWERING`, `PLANNING`, `QUEUED`, `CANCELLED`, `FAILED` |
| `ANSWERING` | `SUCCEEDED`, `CANCELLED`, `FAILED` |
| `PLANNING` | `AWAITING_APPROVAL`, `CANCELLED`, `FAILED` |
| `AWAITING_APPROVAL` | `QUEUED`, `REJECTED`, `CANCELLED`, `FAILED` |
| `QUEUED` | `RUNNING`, `CANCELLED`, `FAILED` |
| `RUNNING` | `VERIFYING`, `CANCELLED`, `FAILED` |
| `VERIFYING` | `SUCCEEDED`, `NEEDS_REVISION`, `CANCELLED`, `FAILED` |
| `NEEDS_REVISION` | `PLANNING`, `QUEUED`, `CANCELLED` |
| `REJECTED` | `PLANNING`, `CANCELLED` |
| `CANCELLED` | `QUEUED` |
| `FAILED` | `QUEUED` |
| `SUCCEEDED` | none |

`Task.transition` returns a new immutable task plus transition evidence. It never
mutates the previous aggregate. The repository updates a task only when its
stored version equals the caller's expected version and appends the evidence in
the same transaction.

## Concurrency and idempotency

Task creation claims `(operation, idempotency_key)` before inserting the task.
Concurrent duplicates return the original entity ID. Task updates use a
compare-and-swap `UPDATE`; a stale writer receives `ConcurrencyConflictError`.
No failed update appends transition history.

Plan approval locks the plan row and validates task ID, plan ID, and plan version
before recording the decision. A decision for version N cannot authorize N+1.

A retry inserts a new `Run` with an incremented attempt and
`previous_run_id`. Previous attempts and evidence are never overwritten.

## Migration policy

SQL migrations live in `src/jarvis/infrastructure/sql`. The migration runner:

1. validates the target schema name;
2. takes a schema-specific PostgreSQL advisory transaction lock;
3. applies pending files in lexical order;
4. stores SHA-256 checksums in `schema_migrations`;
5. rejects edits to an already-applied file.

Run migrations with:

    make migrate

The API container applies migrations before starting Uvicorn. This is safe for
multiple simultaneous starters because of the advisory lock.

## Verification

The M1 acceptance suite proves:

- every declared task edge and every undeclared pair;
- no mutation on rejected transition;
- duplicate command behavior with concurrent PostgreSQL callers;
- one winner and one classified conflict for concurrent stale writers;
- immutable approval version binding;
- retry preservation;
- state recovery through a new repository instance;
- clean-schema migration, repeat migration, and checksum drift rejection;
- artifact, model-resolution, and trace-link persistence.

Integration tests use a generated schema and remove only that exact schema after
the test. The in-memory adapter is for unit tests and is never production proof.
