import { FormEvent, useEffect, useState } from "react";
import {
  fetchEvalSummary,
  fetchEvents,
  fetchMonitorRun,
  fetchPushes,
  fetchTopics,
} from "./api/client";
import type {
  EvalSummary,
  EventListResponse,
  MonitorRun,
  PushRecord,
  Topic,
} from "./api/types";

type Loadable<T> =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; data: T };

const percent = (value?: number) => `${Math.round((value ?? 0) * 100)}%`;

function compactJson(value: unknown) {
  if (value == null) return "-";
  return JSON.stringify(value, null, 2);
}

export default function App() {
  const [topics, setTopics] = useState<Loadable<Topic[]>>({
    status: "loading",
  });
  const [pushes, setPushes] = useState<Loadable<PushRecord[]>>({
    status: "loading",
  });
  const [summary, setSummary] = useState<Loadable<EvalSummary>>({
    status: "loading",
  });
  const [runId, setRunId] = useState("run_001");
  const [run, setRun] = useState<Loadable<MonitorRun> | null>(null);
  const [events, setEvents] = useState<Loadable<EventListResponse> | null>(
    null,
  );

  useEffect(() => {
    fetchTopics()
      .then((data) => setTopics({ status: "ready", data }))
      .catch((error: Error) =>
        setTopics({ status: "error", message: error.message }),
      );
    fetchPushes()
      .then((data) => setPushes({ status: "ready", data: data.pushes ?? [] }))
      .catch((error: Error) =>
        setPushes({ status: "error", message: error.message }),
      );
    fetchEvalSummary()
      .then((data) => setSummary({ status: "ready", data }))
      .catch((error: Error) =>
        setSummary({ status: "error", message: error.message }),
      );
  }, []);

  const loadRun = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = runId.trim();
    if (!trimmed) return;
    setRun({ status: "loading" });
    setEvents({ status: "loading" });
    fetchMonitorRun(trimmed)
      .then((data) => setRun({ status: "ready", data }))
      .catch((error: Error) =>
        setRun({ status: "error", message: error.message }),
      );
    fetchEvents(trimmed)
      .then((data) => setEvents({ status: "ready", data }))
      .catch((error: Error) =>
        setEvents({ status: "error", message: error.message }),
      );
  };

  const topicCount = topics.status === "ready" ? topics.data.length : 0;
  const pushCount = pushes.status === "ready" ? pushes.data.length : 0;
  const toolSuccess =
    summary.status === "ready" ? percent(summary.data.avg_tool_success_rate) : "-";
  const traceCompleteness =
    summary.status === "ready"
      ? percent(summary.data.avg_trace_completeness)
      : "-";

  return (
    <main className="shell">
      <section className="hero">
        <div>
          <p className="eyebrow">Phase 2 Operations Console</p>
          <h1>Industry News Agent Dashboard</h1>
          <p className="hero-copy">
            Monitor topics, push decisions, trace events, and quality signals
            from the existing FastAPI backend.
          </p>
        </div>
        <form className="run-search" onSubmit={loadRun}>
          <label htmlFor="run-id">Run ID</label>
          <div>
            <input
              id="run-id"
              value={runId}
              onChange={(event) => setRunId(event.target.value)}
            />
            <button type="submit">Load run</button>
          </div>
        </form>
      </section>

      <section className="metric-grid" aria-label="Dashboard summary">
        <article className="metric-card">
          <span>Topics</span>
          <strong>{topicCount}</strong>
        </article>
        <article className="metric-card">
          <span>Push records</span>
          <strong>{pushCount}</strong>
        </article>
        <article className="metric-card">
          <span>Tool success</span>
          <strong>{toolSuccess}</strong>
        </article>
        <article className="metric-card">
          <span>Trace completeness</span>
          <strong>{traceCompleteness}</strong>
        </article>
      </section>

      {summary.status === "error" && (
        <section className="inline-notice">
          Quality summary is not available yet: {summary.message}
        </section>
      )}

      <section className="panel-grid">
        <section className="panel">
          <h2>Topics</h2>
          {topics.status === "loading" && <p>Loading topics...</p>}
          {topics.status === "error" && <p className="error">{topics.message}</p>}
          {topics.status === "ready" && topics.data.length === 0 && (
            <p>No topics configured.</p>
          )}
          {topics.status === "ready" &&
            topics.data.map((topic) => (
              <article className="row-card" key={topic.topic_id}>
                <h3>{topic.name}</h3>
                <p>{topic.description}</p>
                <p>Keywords: {topic.seed_keywords.join(", ") || "-"}</p>
                <p>Trusted: {topic.trusted_sources.join(", ") || "-"}</p>
                <p>
                  Threshold {topic.push_threshold} | Enabled{" "}
                  {topic.enabled ? "yes" : "no"} | Cron{" "}
                  {topic.schedule_cron ?? "-"}
                </p>
              </article>
            ))}
        </section>

        <section className="panel">
          <h2>Pushes</h2>
          {pushes.status === "loading" && <p>Loading pushes...</p>}
          {pushes.status === "error" && <p className="error">{pushes.message}</p>}
          {pushes.status === "ready" && pushes.data.length === 0 && (
            <p>No push records yet.</p>
          )}
          {pushes.status === "ready" &&
            pushes.data.map((push) => (
              <article className="row-card" key={push.push_id}>
                <h3>{push.push_id}</h3>
                <p>
                  Run {push.run_id} | Candidate {push.candidate_id}
                </p>
                <p>
                  Score {push.score} | Push {push.should_push ? "yes" : "no"}
                </p>
                <p>{push.decision_reason ?? "No decision reason"}</p>
              </article>
            ))}
        </section>
      </section>

      <section className="panel-grid">
        <section className="panel">
          <h2>Run Detail</h2>
          {run === null && <p>Enter a run id to inspect monitor state.</p>}
          {run?.status === "loading" && <p>Loading run...</p>}
          {run?.status === "error" && <p className="error">{run.message}</p>}
          {run?.status === "ready" && (
            <div className="state-block">
              <p>
                Status: {run.data.status} | Trigger: {run.data.trigger}
              </p>
              <p>
                Expanded queries:{" "}
                {(run.data.expanded_queries ?? []).length > 0
                  ? (run.data.expanded_queries ?? []).map((query) => (
                      <span className="query-pill" key={query}>
                        {query}
                      </span>
                    ))
                  : "-"}
              </p>
              <p>Candidates: {(run.data.candidate_items ?? []).length}</p>
              <p>Decisions: {(run.data.final_decisions ?? []).length}</p>
              <pre>{compactJson(run.data.errors ?? [])}</pre>
            </div>
          )}
        </section>

        <section className="panel">
          <h2>Trace Timeline</h2>
          {events === null && <p>Trace events appear after loading a run.</p>}
          {events?.status === "loading" && <p>Loading events...</p>}
          {events?.status === "error" && (
            <p className="error">{events.message}</p>
          )}
          {events?.status === "ready" && events.data.events.length === 0 && (
            <p>No trace events found.</p>
          )}
          {events?.status === "ready" &&
            events.data.events.map((event) => (
              <article className="timeline-item" key={event.event_id}>
                <span>{event.event_type}</span>
                <h3>{event.node}</h3>
                <p>{event.message}</p>
                <pre>{compactJson(event.payload ?? {})}</pre>
              </article>
            ))}
        </section>
      </section>
    </main>
  );
}
