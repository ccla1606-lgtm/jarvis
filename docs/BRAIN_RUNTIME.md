# Brain runtime

## Responsibility split

Jarvis owns the task, plan, approval, run, and transition records. LangGraph
owns only the execution cursor and node-state projection. Replacing LangGraph,
LangSmith, or Agent Server must not change the domain model.

The graph is deliberately explicit:

1. `intake`
2. `triage`
3. one of `fast`, `bounded`, or `planned`
4. fast finalization, bounded queueing, or finite plan validation
5. an interrupt that waits for an approval already committed to Jarvis state

LLM output never names a Python callable. It produces a schema-validated route
enum or a typed plan; deterministic edges and validators select the next node.

## Budgets

Every execution has hard limits for graph steps, total normalized model tokens,
wall-clock execution time, plan steps, and triage repairs. Human approval wait
time is excluded by resetting the execution deadline before resume. The other
budgets remain cumulative across the workflow.

## Plans and scope

Each plan step records dependencies, tools, and repositories. Before a plan is
persisted, Jarvis rejects:

- missing dependencies;
- dependency cycles;
- non-consecutive positions;
- excess step count;
- tools or repositories outside the request scope;
- tool use when side effects are disabled.

Plan version 1 is reused after node replay, so a checkpoint retry does not
create a second plan.

## Runtimes

`LangGraphBrainRuntime.local()` uses `InMemorySaver` for tests and local
debugging only. `postgres_brain_runtime()` uses the official PostgreSQL
checkpointer, calls `setup()`, selects an isolated schema, and configures
strict safe serialization. Reconstructing the runtime with the same PostgreSQL
schema and task ID resumes the same graph thread.

Neither runtime requires LangSmith or a production Agent Server. A composed
runtime exposes `mermaid()` for development visualization.

## Default API composition (M4.1)

`create_app()` now owns the production-shaped graph lifecycle when no repository or runtime is injected. FastAPI startup opens the PostgreSQL checkpointer, runs its setup, binds one `LangGraphBrainRuntime`, and only then serves task commands. Shutdown clears the handle and closes the model gateway. API approval and rejection commands first commit the exact plan decision, then resume the matching interrupted graph thread.

Repository or runtime injection remains an explicit test seam: supplying either prevents hidden PostgreSQL and provider startup. Development and test environments use the deterministic model adapter; production validation requires live mode and both provider credentials.

The integration acceptance test uses the default composition root and a real PostgreSQL schema. It proves fast completion, planned interruption, persisted plans and transitions, approval resume, SSE cursor recovery, and resume after a fresh application lifecycle.

## References

- [LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [PostgreSQL checkpointer package](https://pypi.org/project/langgraph-checkpoint-postgres/)
