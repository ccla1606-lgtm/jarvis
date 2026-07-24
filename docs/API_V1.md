# Jarvis API v1

The v1 API is the durable control-plane boundary for tasks, plans, approvals,
attempts, and transition history. FastAPI generates the runtime schema at
`/openapi.json`; the reviewed snapshot is [openapi.v1.json](openapi.v1.json).

## Authentication

Every `/v1/tasks` endpoint requires:

    Authorization: Bearer <JARVIS_API_TOKEN>

The default token is intentionally limited to local development. Production
configuration refuses to start with the default value. Health endpoints and the
temporary `/v1/demo` compatibility endpoint are public.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/v1/tasks` | Submit one idempotent task command |
| `GET` | `/v1/tasks` | List canonical tasks |
| `GET` | `/v1/tasks/{task_id}` | Rebuild task detail from durable state |
| `POST` | `/v1/tasks/{task_id}/approve` | Approve one exact plan ID and version |
| `POST` | `/v1/tasks/{task_id}/reject` | Reject one exact plan ID and version |
| `POST` | `/v1/tasks/{task_id}/cancel` | Idempotently cancel a task |
| `POST` | `/v1/tasks/{task_id}/retry` | Create a linked attempt from a retryable run |
| `GET` | `/v1/tasks/{task_id}/events` | Read transition events after a cursor |

`POST /v1/tasks` also requires an `Idempotency-Key` header. Repeating a
submission with the same key returns the original Task instead of creating a
second canonical record.

## Approval boundary

Approval is never inferred from chat text. The caller sends both `plan_id` and
`plan_version`; a mismatch returns `STALE_PLAN` and creates no run. A successful
approval moves the task to `QUEUED` and creates a run referencing that exact
immutable plan version. Rejection creates no run.

## Errors and correlation

Errors use one stable envelope:

```json
{
  "error": {
    "code": "STALE_PLAN",
    "message": "safe diagnostic text",
    "correlation_id": "request-or-server-generated-id"
  }
}
```

Clients may send `X-Correlation-ID` containing 1–128 letters, digits, dots,
underscores, or hyphens. The same value is returned in the response header and
error envelope. Invalid or missing values are replaced with a generated UUID.

Stable codes currently include `UNAUTHORIZED`, `INVALID_PAYLOAD`,
`INVALID_CURSOR`, `NOT_FOUND`, `STALE_PLAN`, `VERSION_CONFLICT`,
`INVALID_TRANSITION`, `INVALID_RETRY`, `DOMAIN_CONFLICT`, and `INTERNAL_ERROR`.

## Graph execution and approval resume

The default application composition runs every accepted task through LangGraph and persists both domain state and checkpoints in PostgreSQL. Read-only objectives may complete on the fast route before the submission response returns. Side-effecting objectives persist an immutable plan and stop at `AWAITING_APPROVAL`.

Approval and rejection payloads must identify the exact persisted plan ID and version. The command is committed before the graph is resumed with that same signal. A process restart is safe: a new application lifecycle resolves the checkpoint by task ID and resumes the interrupted thread.

## SSE cursor semantics

Task transitions are immutable and use the task version as their SSE event ID.
Send either `Last-Event-ID` or `after_version` to receive only later
transitions. The endpoint returns the currently available ordered batch and
closes; a client reconnects using the last accepted ID. This keeps delivery
resumable without making SSE the canonical history.

## Contract workflow

Regenerate the reviewed schema after changing Pydantic API models:

    make openapi

`make verify` fails when the snapshot is stale. The web client fixture is parsed
by the same Pydantic response model and type-checked by TypeScript, preventing
the UI and API contracts from drifting silently.
