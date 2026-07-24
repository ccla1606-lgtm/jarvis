ALTER TABLE approvals
    ADD CONSTRAINT approvals_plan_version_unique
    UNIQUE (plan_id, plan_version);

CREATE UNIQUE INDEX runs_previous_run_id_unique
    ON runs (previous_run_id)
    WHERE previous_run_id IS NOT NULL;
