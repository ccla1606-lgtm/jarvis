CREATE TABLE tasks (
    id UUID PRIMARY KEY,
    objective TEXT NOT NULL CHECK (length(btrim(objective)) > 0),
    status TEXT NOT NULL CHECK (
        status IN (
            'RECEIVED',
            'TRIAGING',
            'ANSWERING',
            'PLANNING',
            'AWAITING_APPROVAL',
            'QUEUED',
            'RUNNING',
            'VERIFYING',
            'SUCCEEDED',
            'REJECTED',
            'CANCELLED',
            'FAILED',
            'NEEDS_REVISION'
        )
    ),
    version INTEGER NOT NULL CHECK (version >= 0),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CHECK (updated_at >= created_at)
);

CREATE TABLE task_transitions (
    id UUID PRIMARY KEY,
    task_id UUID NOT NULL REFERENCES tasks(id),
    run_id UUID NULL,
    from_status TEXT NOT NULL,
    to_status TEXT NOT NULL,
    task_version INTEGER NOT NULL CHECK (task_version > 0),
    actor TEXT NOT NULL CHECK (length(btrim(actor)) > 0),
    reason TEXT NOT NULL CHECK (length(btrim(reason)) > 0),
    occurred_at TIMESTAMPTZ NOT NULL,
    UNIQUE (task_id, task_version)
);

CREATE INDEX task_transitions_task_time_idx
    ON task_transitions (task_id, occurred_at, task_version);

CREATE TABLE plans (
    id UUID PRIMARY KEY,
    task_id UUID NOT NULL REFERENCES tasks(id),
    version INTEGER NOT NULL CHECK (version > 0),
    status TEXT NOT NULL CHECK (status IN ('PROPOSED', 'APPROVED', 'REJECTED', 'SUPERSEDED')),
    steps JSONB NOT NULL CHECK (jsonb_typeof(steps) = 'array' AND jsonb_array_length(steps) > 0),
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (task_id, version),
    UNIQUE (id, version)
);

CREATE TABLE approvals (
    id UUID PRIMARY KEY,
    task_id UUID NOT NULL REFERENCES tasks(id),
    plan_id UUID NOT NULL,
    plan_version INTEGER NOT NULL CHECK (plan_version > 0),
    decision TEXT NOT NULL CHECK (decision IN ('APPROVED', 'REJECTED')),
    actor TEXT NOT NULL CHECK (length(btrim(actor)) > 0),
    reason TEXT NOT NULL CHECK (length(btrim(reason)) > 0),
    created_at TIMESTAMPTZ NOT NULL,
    FOREIGN KEY (plan_id, plan_version) REFERENCES plans(id, version)
);

CREATE TABLE runs (
    id UUID PRIMARY KEY,
    task_id UUID NOT NULL REFERENCES tasks(id),
    attempt INTEGER NOT NULL CHECK (attempt > 0),
    status TEXT NOT NULL CHECK (
        status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED', 'NEEDS_REVISION')
    ),
    plan_id UUID NULL REFERENCES plans(id),
    plan_version INTEGER NULL,
    previous_run_id UUID NULL REFERENCES runs(id),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE (task_id, attempt),
    CHECK ((plan_id IS NULL) = (plan_version IS NULL)),
    CHECK (plan_version IS NULL OR plan_version > 0),
    CHECK (updated_at >= created_at)
);

ALTER TABLE task_transitions
    ADD CONSTRAINT task_transitions_run_id_fkey
    FOREIGN KEY (run_id) REFERENCES runs(id);

CREATE TABLE idempotency_records (
    operation TEXT NOT NULL,
    idempotency_key TEXT NOT NULL CHECK (length(btrim(idempotency_key)) > 0),
    entity_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (operation, idempotency_key)
);

CREATE TABLE artifacts (
    id UUID PRIMARY KEY,
    task_id UUID NOT NULL REFERENCES tasks(id),
    run_id UUID NULL REFERENCES runs(id),
    kind TEXT NOT NULL,
    uri TEXT NOT NULL,
    sha256 CHAR(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE model_resolutions (
    id UUID PRIMARY KEY,
    task_id UUID NOT NULL REFERENCES tasks(id),
    run_id UUID NULL REFERENCES runs(id),
    profile TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    account TEXT NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE trace_links (
    id UUID PRIMARY KEY,
    task_id UUID NOT NULL REFERENCES tasks(id),
    run_id UUID NULL REFERENCES runs(id),
    backend TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    url TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (backend, trace_id, task_id, run_id)
);
