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

## References

- [LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [PostgreSQL checkpointer package](https://pypi.org/project/langgraph-checkpoint-postgres/)
