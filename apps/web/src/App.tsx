import { useEffect, useState } from "react";

import { fetchHealth, type HealthResponse } from "./api";
import "./styles.css";

type ViewState =
  | { kind: "checking" }
  | { kind: "online"; health: HealthResponse }
  | { kind: "offline"; reason: string };

const modules = [
  "LangGraph brain",
  "Provider gateway",
  "Context compiler",
  "Agent Host",
  "OpenTelemetry",
];

export function App() {
  const [state, setState] = useState<ViewState>({ kind: "checking" });

  useEffect(() => {
    const controller = new AbortController();
    fetchHealth(fetch, controller.signal)
      .then((health) => setState({ kind: "online", health }))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          const reason = error instanceof Error ? error.message : "Unknown readiness error";
          setState({ kind: "offline", reason });
        }
      });
    return () => controller.abort();
  }, []);

  return (
    <main className="shell">
      <header className="hero">
        <div>
          <p className="eyebrow">JARVIS CONTROL PLANE</p>
          <h1>One durable view of tasks, agents, and evidence.</h1>
          <p className="lede">
            The M0 scaffold proves the API, UI, PostgreSQL, telemetry collector, and
            reproducible development environment.
          </p>
        </div>
        <section className={`status status--${state.kind}`} aria-live="polite">
          <span className="status__dot" />
          <div>
            <strong>
              {state.kind === "checking"
                ? "Checking system"
                : state.kind === "online"
                  ? "System ready"
                  : "System unavailable"}
            </strong>
            <p>
              {state.kind === "online"
                ? state.health.detail
                : state.kind === "offline"
                  ? state.reason
                  : "Waiting for the API readiness probe"}
            </p>
          </div>
        </section>
      </header>

      <section className="grid" aria-label="Planned modules">
        {modules.map((module, index) => (
          <article className="module" key={module}>
            <span>0{index + 1}</span>
            <h2>{module}</h2>
            <p>Typed boundary · bounded execution · correlated evidence</p>
          </article>
        ))}
      </section>

      <footer>
        M0 · executable foundation · provider and CLI adapters arrive in later milestones
      </footer>
    </main>
  );
}

