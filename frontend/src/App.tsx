import { FormEvent, useEffect, useState } from "react";
import {
  fetchCandidateTasks,
  fetchEvalSummary,
  fetchEvents,
  fetchMonitorRun,
  fetchPushes,
  fetchTopics,
} from "./api/client";
import type {
  CandidateTaskListResponse,
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

function runtimeFlagLabel(value?: boolean) {
  if (value === true) return "yes";
  if (value === false) return "no";
  return "-";
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
  const [runId, setRunId] = useState("run_demo_bootstrap");
  const [run, setRun] = useState<Loadable<MonitorRun> | null>(null);
  const [events, setEvents] = useState<Loadable<EventListResponse> | null>(
    null,
  );
  const [candidateTasks, setCandidateTasks] =
    useState<Loadable<CandidateTaskListResponse> | null>(null);

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
    setCandidateTasks({ status: "loading" });

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
    fetchCandidateTasks(trimmed)
      .then((data) => setCandidateTasks({ status: "ready", data }))
      .catch((error: Error) =>
        setCandidateTasks({ status: "error", message: error.message }),
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
  const recallProxy =
    summary.status === "ready"
      ? percent(summary.data.avg_candidate_recall_proxy)
      : "-";
  const taskFailureRate =
    summary.status === "ready"
      ? percent(summary.data.avg_candidate_task_failure_rate)
      : "-";
  const avgEventLatency =
    summary.status === "ready"
      ? `${summary.data.avg_event_latency_ms} ms`
      : "-";
  const fallbackTotal =
    summary.status === "ready"
      ? summary.data.total_raw_summary_count +
        summary.data.total_browser_fallback_count +
        summary.data.total_provider_fallback_count
      : 0;
  const candidateTaskItems =
    candidateTasks?.status === "ready" ? candidateTasks.data.items ?? [] : [];
  const runContext =
    run?.status === "ready" ? run.data.run_context ?? {} : {};
  const businessMemory =
    run?.status === "ready" ? run.data.business_memory ?? {} : {};
  const businessContext =
    run?.status === "ready" ? run.data.business_memory?.business_context ?? {} : {};
  const semanticMemory =
    businessContext.semantic_memory &&
    typeof businessContext.semantic_memory === "object"
      ? businessContext.semantic_memory
      : {};
  const ragEvalMetrics =
    run?.status === "ready" ? run.data.evaluation_output?.eval_result ?? {} : {};
  const integrationRuntime =
    run?.status === "ready" ? run.data.integration_runtime ?? {} : {};
  const historyIndexResult =
    run?.status === "ready" ? run.data.history_index_result ?? {} : {};
  const historyIndexSearch =
    historyIndexResult.search && typeof historyIndexResult.search === "object"
      ? historyIndexResult.search
      : {};
  const pushHistoryCount = Array.isArray(businessMemory.push_history)
    ? businessMemory.push_history.length
    : 0;
  const memoryDocumentCount = Array.isArray(businessMemory.documents)
    ? businessMemory.documents.length
    : 0;

  return (
    <main className="shell">
      <section className="hero">
        <div>
          <p className="eyebrow">Operations Console</p>
          <h1>Industry News Agent Dashboard</h1>
          <p className="hero-copy">
            Resume-facing operations view for the real multi-agent monitor loop:
            topic planning, candidate retrieval, extraction, evaluation, queue
            governance, and quality signals.
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
          <p className="run-hint">
            Defaulting to the reproducible demo evidence chain:
            <code>run_demo_bootstrap</code>.
          </p>
        </form>
      </section>

      <section className="story-grid" aria-label="Architecture and governance">
        <article className="story-card">
          <p className="eyebrow">Multi-Agent Pipeline</p>
          <h2>
            Supervisor -&gt; Planner -&gt; Retrieval -&gt;
            CandidateTaskOrchestrator -&gt; Finalize
          </h2>
          <p>
            The backend no longer presents a flat helper chain. A supervisor
            controls run lifecycle while planner and retrieval stay top-level,
            then candidate fetch, extract, and evaluate work runs inside the
            orchestrator under one structured LangGraph contract.
          </p>
        </article>
        <article className="story-card">
          <p className="eyebrow">Queue Governance</p>
          <h2>APScheduler, queue, worker, retry, active-run guard</h2>
          <p>
            Scheduled topics enqueue work, workers consume runs, and governance
            events record dequeue timing, retry decisions, timeout handling, and
            duplicate-active-run protection.
          </p>
        </article>
        <article className="story-card">
          <p className="eyebrow">Quality and fallback signals</p>
          <h2>
            Trace completeness, recall proxy, latency proxy, failure-rate proxy
            evidence
          </h2>
          <p>
            Evaluation persists run quality metrics so the project can show how
            retrieval and extraction quality are observed instead of treated as
            opaque model output. These are proxy metrics for the current MVP
            runtime, not overstated production observability claims.
          </p>
        </article>
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
          <h2>Governance Snapshot</h2>
          <p className="panel-copy">
            This panel summarizes the operational story that supports the resume
            claim around scheduled monitoring and queued worker execution.
          </p>
          <article className="row-card">
            <h3>Execution path</h3>
            <p>
              Manual trigger or APScheduler enqueue {"->"} worker dequeue {"->"}{" "}
              monitor graph invocation.
            </p>
            <p>Redis Stream is used when available, with in-memory queue fallback.</p>
          </article>
          <article className="row-card">
            <h3>Failure handling</h3>
            <p>Workers emit retry, timeout, and active-run-guard governance events.</p>
            <p>Failed runs are persisted instead of being silently dropped.</p>
            <p>
              Candidate-stage reliability stays within bounded in-process
              concurrency plus retry and timeout controls, not a distributed
              worker fleet or full circuit-breaker system.
            </p>
          </article>
        </section>

        <section className="panel">
          <h2>Quality Snapshot</h2>
          <p className="panel-copy">
            These values come from persisted eval summaries and are labeled as
            proxy signals where the implementation is heuristic or runtime-local,
            not production KPI claims.
          </p>
          {summary.status === "loading" && <p>Loading quality summary...</p>}
          {summary.status === "error" && (
            <p className="error">{summary.message}</p>
          )}
          {summary.status === "ready" && (
              <>
                <article className="row-card">
                <h3>Observed proxy metrics</h3>
                <p>Run count {summary.data.run_count}</p>
                <p>Total push records {summary.data.total_push_count}</p>
                <p>Fallback count {fallbackTotal}</p>
                <p>Recall proxy {recallProxy}</p>
                <p>Task failure-rate proxy {taskFailureRate}</p>
                <p>Avg event latency proxy {avgEventLatency}</p>
                <p>
                  False-positive proxy total{" "}
                  {summary.data.total_false_positive_proxy_count}
                </p>
              </article>
              <article className="row-card">
                <h3>Latest eval</h3>
                <p>Latest run {summary.data.latest_eval.run_id}</p>
                <p>Judge mode {summary.data.latest_eval.judge_mode ?? "mock_rule_judge"}</p>
                <p>
                  Runtime cost proxy units: tools{" "}
                  {summary.data.latest_eval.runtime_cost_proxy?.tool_calls ?? 0} |
                  browser fallbacks{" "}
                  {summary.data.latest_eval.runtime_cost_proxy?.browser_fallbacks ?? 0}
                  {" | "}model decisions{" "}
                  {summary.data.latest_eval.runtime_cost_proxy?.model_decisions ?? 0}
                </p>
                <p>
                  Suggestions:{" "}
                  {(summary.data.latest_eval.suggestions ?? []).join(", ") || "-"}
                </p>
              </article>
            </>
          )}
        </section>
      </section>

      <section className="panel-grid">
        <section className="panel">
          <h2>Topics</h2>
          <p className="panel-copy">
            Topics define the monitoring intent, trusted sources, threshold, and
            scheduler registration settings.
          </p>
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
                  {topic.enabled ? "yes" : "no"} | Cron {topic.schedule_cron ?? "-"}
                </p>
              </article>
            ))}
        </section>

        <section className="panel">
          <h2>Pushes</h2>
          <p className="panel-copy">
            Push records are the persisted outcome of evaluation, not transient UI
            state.
          </p>
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
          <p className="panel-copy">
            This view promotes the structured stage contracts into the primary
            read surface while keeping compatibility mirrors visible for concise
            readback.
          </p>
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
              {run.data.candidate_task_summary && (
                <>
                  <p>
                    Candidate task orchestration:{" "}
                    {run.data.candidate_task_summary.task_count ?? 0} tasks | completed{" "}
                    {run.data.candidate_task_summary.completed_count ?? 0} | skipped{" "}
                    {run.data.candidate_task_summary.skipped_count ?? 0} | failed{" "}
                    {run.data.candidate_task_summary.failed_count ?? 0}
                  </p>
                  <p>
                    Stage evidence: fetch{" "}
                    {run.data.candidate_task_summary.fetch_completed_count ?? 0} |
                    extract{" "}
                    {run.data.candidate_task_summary.extract_completed_count ?? 0} |
                    evaluate{" "}
                    {run.data.candidate_task_summary.evaluate_completed_count ?? 0}
                  </p>
                </>
              )}
              <article className="row-card">
                <h3>Structured stage read surface</h3>
                <p>
                  The dashboard reads the same structured planner, retrieval,
                  extraction, and evaluation sections that the backend exposes on
                  the run API.
                </p>
              </article>
              <div className="structured-grid">
                <article className="row-card">
                  <h3>Planner output</h3>
                  <p>
                    Expanded queries{" "}
                    {run.data.planner_output?.expanded_queries?.length ?? 0} | source
                    plan steps {run.data.planner_output?.source_plan?.length ?? 0}
                  </p>
                  <p>
                    {(run.data.planner_output?.planning_reasons ?? []).join(" ") ||
                      "No planning reasons recorded."}
                  </p>
                  <pre>{compactJson(run.data.planner_output ?? {})}</pre>
                </article>
                <article className="row-card">
                  <h3>Retrieval output</h3>
                  <p>
                    Candidate pool{" "}
                    {run.data.retrieval_output?.candidate_pool?.length ?? 0} |
                    provider fallbacks{" "}
                    {run.data.retrieval_output?.provider_fallbacks?.length ?? 0}
                  </p>
                  <pre>{compactJson(run.data.retrieval_output ?? {})}</pre>
                </article>
                <article className="row-card">
                  <h3>Extraction output</h3>
                  <p>
                    Fetched contents{" "}
                    {run.data.extraction_output?.fetched_contents?.length ?? 0} |
                    evidence items{" "}
                    {run.data.extraction_output?.evidence_items?.length ?? 0}
                  </p>
                  <pre>{compactJson(run.data.extraction_output ?? {})}</pre>
                </article>
                <article className="row-card">
                  <h3>Evaluation output</h3>
                  <p>
                    Final decisions{" "}
                    {run.data.evaluation_output?.final_decisions?.length ?? 0} |
                    push records {run.data.evaluation_output?.push_records?.length ?? 0}
                  </p>
                  <pre>{compactJson(run.data.evaluation_output ?? {})}</pre>
                </article>
              </div>
              <article className="row-card">
                <h3>Run context and business memory</h3>
                <p>
                  These fields expose request-level runtime framing and the
                  durable business grounding that planner and evaluation can
                  read during the monitor loop.
                </p>
              </article>
              <div className="structured-grid">
                <article className="row-card">
                  <h3>Run context</h3>
                  <p>Run context keys {Object.keys(runContext).length}</p>
                  <pre>{compactJson(runContext)}</pre>
                </article>
                <article className="row-card">
                  <h3>Business memory</h3>
                  <p>
                    Push history {pushHistoryCount} | documents{" "}
                    {memoryDocumentCount}
                  </p>
                  <pre>{compactJson(businessMemory)}</pre>
                </article>
              </div>
              <div className="structured-grid">
                <article className="row-card">
                  <h3>RAG grounding runtime</h3>
                  <p>
                    Retrieval mode {businessContext.retrieval_mode ?? "-"} | retrievers{" "}
                    {businessContext.retrievers?.join(", ") || "-"}
                  </p>
                  <p>
                    Semantic keywords {semanticMemory.topic_keywords?.length ?? 0} |
                    trusted sources {semanticMemory.trusted_source_hints?.length ?? 0} |
                    push rules {semanticMemory.push_rules?.length ?? 0}
                  </p>
                  <p>
                    RAG guidance applied{" "}
                    {ragEvalMetrics.rag_guidance_applied_count ?? 0} | trusted
                    matches {ragEvalMetrics.trusted_source_match_count ?? 0} |
                    rule hits {ragEvalMetrics.rule_guidance_hits ?? 0}
                  </p>
                  <pre>{compactJson(businessContext)}</pre>
                </article>
              </div>
              <div className="structured-grid">
                <article className="row-card">
                  <h3>History index runtime</h3>
                  <p>Provider {historyIndexResult.provider ?? "-"}</p>
                  <p>
                    Indexed {historyIndexResult.indexed_count ?? 0} | search results{" "}
                    {historyIndexSearch.returned_count ??
                      (Array.isArray(historyIndexSearch.items)
                        ? historyIndexSearch.items.length
                        : 0)}
                  </p>
                  <p>Query {historyIndexSearch.query ?? "-"}</p>
                  <pre>{compactJson(historyIndexResult)}</pre>
                </article>
              </div>
              <div className="structured-grid">
                <article className="row-card">
                  <h3>Tool access runtime</h3>
                  <p>
                    Selected path {integrationRuntime.mcp?.selected_tool_path ?? "-"} |
                    base URL configured{" "}
                    {runtimeFlagLabel(
                      integrationRuntime.mcp?.base_url_configured,
                    )}{" "}
                    | tool calls {integrationRuntime.mcp?.tool_call_count ?? 0}
                  </p>
                  <p>
                    Browser selected path{" "}
                    {integrationRuntime.browser?.selected_tool_path ?? "-"} | base URL
                    configured{" "}
                    {runtimeFlagLabel(
                      integrationRuntime.browser?.base_url_configured,
                    )}
                  </p>
                  <p>
                    Notification selected path{" "}
                    {integrationRuntime.notification?.selected_tool_path ?? "-"}
                  </p>
                </article>
                <article className="row-card">
                  <h3>MCP runtime</h3>
                  <p>
                    Configured provider{" "}
                    {run.data.integration_runtime?.mcp?.configured_provider ?? "-"}
                  </p>
                  <p>
                    Enabled{" "}
                    {runtimeFlagLabel(run.data.integration_runtime?.mcp?.enabled)} |
                    used in run{" "}
                    {runtimeFlagLabel(run.data.integration_runtime?.mcp?.used_in_run)} |
                    fallback used{" "}
                    {runtimeFlagLabel(run.data.integration_runtime?.mcp?.fallback_used)}
                  </p>
                </article>
                <article className="row-card">
                  <h3>Browser fallback runtime</h3>
                  <p>
                    Configured provider{" "}
                    {run.data.integration_runtime?.browser?.configured_provider ?? "-"}
                  </p>
                  <p>
                    Enabled{" "}
                    {runtimeFlagLabel(run.data.integration_runtime?.browser?.enabled)} |
                    used in run{" "}
                    {runtimeFlagLabel(
                      run.data.integration_runtime?.browser?.used_in_run,
                    )}{" "}
                    | fallback used{" "}
                    {runtimeFlagLabel(
                      run.data.integration_runtime?.browser?.fallback_used,
                    )}
                  </p>
                  <p>
                    Allowed domains:{" "}
                    {run.data.integration_runtime?.browser?.allowed_domains?.join(", ") ||
                      "-"}
                  </p>
                  <p>
                    Attempts{" "}
                    {run.data.integration_runtime?.browser?.browser_attempt_count ?? 0} |
                    blocked{" "}
                    {run.data.integration_runtime?.browser?.browser_blocked_count ?? 0} |
                    last provider{" "}
                    {run.data.integration_runtime?.browser?.last_browser_provider ?? "-"}
                  </p>
                  <p>
                    Failure reason{" "}
                    {run.data.integration_runtime?.browser?.browser_failure_reason ??
                      "-"}
                  </p>
                </article>
                <article className="row-card">
                  <h3>Notification runtime</h3>
                  <p>
                    Configured provider{" "}
                    {run.data.integration_runtime?.notification?.configured_provider ??
                      "-"}
                  </p>
                  <p>
                    Enabled{" "}
                    {runtimeFlagLabel(
                      run.data.integration_runtime?.notification?.enabled,
                    )}{" "}
                    | used in run{" "}
                    {runtimeFlagLabel(
                      run.data.integration_runtime?.notification?.used_in_run,
                    )}{" "}
                    | delivery succeeded{" "}
                    {runtimeFlagLabel(
                      run.data.integration_runtime?.notification?.delivery_succeeded,
                    )}
                  </p>
                  <p>
                    Delivery attempted{" "}
                    {runtimeFlagLabel(
                      run.data.integration_runtime?.notification?.delivery_attempted,
                    )}{" "}
                    | failure code{" "}
                    {run.data.integration_runtime?.notification?.failure_code ?? "-"}
                  </p>
                </article>
                <article className="row-card">
                  <h3>Tool access contract</h3>
                  <p>
                    Contract{" "}
                    {run.data.integration_runtime?.tool_access?.contract ?? "-"}
                  </p>
                  <p>
                    Search path{" "}
                    {run.data.integration_runtime?.tool_access?.search?.provider_path ??
                      "-"}
                    {" | "}tool{" "}
                    {run.data.integration_runtime?.tool_access?.search?.tool_name ?? "-"}
                  </p>
                  <p>
                    Search calls{" "}
                    {run.data.integration_runtime?.tool_access?.search?.tool_call_count ?? 0}
                    {" | "}success{" "}
                    {run.data.integration_runtime?.tool_access?.search?.success_count ?? 0}
                    {" | "}failed{" "}
                    {run.data.integration_runtime?.tool_access?.search?.failure_count ?? 0}
                    {" | "}used{" "}
                    {runtimeFlagLabel(
                      run.data.integration_runtime?.tool_access?.search?.used_in_run,
                    )}
                    {" | "}fallback{" "}
                    {runtimeFlagLabel(
                      run.data.integration_runtime?.tool_access?.search?.fallback_used,
                    )}
                  </p>
                  <p>
                    Browser path{" "}
                    {run.data.integration_runtime?.tool_access?.browser?.provider_path ??
                      "-"}
                    {" | "}tool{" "}
                    {run.data.integration_runtime?.tool_access?.browser?.tool_name ??
                      "-"}
                  </p>
                  <p>
                    Browser calls{" "}
                    {run.data.integration_runtime?.tool_access?.browser?.tool_call_count ?? 0}
                    {" | "}success{" "}
                    {run.data.integration_runtime?.tool_access?.browser?.success_count ?? 0}
                    {" | "}failed{" "}
                    {run.data.integration_runtime?.tool_access?.browser?.failure_count ?? 0}
                    {" | "}used{" "}
                    {runtimeFlagLabel(
                      run.data.integration_runtime?.tool_access?.browser?.used_in_run,
                    )}
                    {" | "}fallback{" "}
                    {runtimeFlagLabel(
                      run.data.integration_runtime?.tool_access?.browser?.fallback_used,
                    )}
                  </p>
                  <p>
                    Notification path{" "}
                    {run.data.integration_runtime?.tool_access?.notification
                      ?.provider_path ?? "-"}
                    {" | "}tool{" "}
                    {run.data.integration_runtime?.tool_access?.notification?.tool_name ??
                      "-"}
                  </p>
                  <p>
                    Notification calls{" "}
                    {run.data.integration_runtime?.tool_access?.notification
                      ?.tool_call_count ?? 0}
                    {" | "}success{" "}
                    {run.data.integration_runtime?.tool_access?.notification
                      ?.success_count ?? 0}
                    {" | "}failed{" "}
                    {run.data.integration_runtime?.tool_access?.notification
                      ?.failure_count ?? 0}
                    {" | "}used{" "}
                    {runtimeFlagLabel(
                      run.data.integration_runtime?.tool_access?.notification
                        ?.used_in_run,
                    )}
                    {" | "}fallback{" "}
                    {runtimeFlagLabel(
                      run.data.integration_runtime?.tool_access?.notification
                        ?.fallback_used,
                    )}
                  </p>
                  {(
                    run.data.integration_runtime?.tool_access?.calls ?? []
                  ).length > 0 && (
                    <div>
                      {(run.data.integration_runtime?.tool_access?.calls ?? []).map(
                        (call, index) => (
                          <p key={`${call.capability ?? "call"}-${index}`}>
                            {call.capability ?? "-"} via {call.provider_path ?? "-"}
                            {" | "}provider {call.provider ?? "-"}
                            {" | "}success {runtimeFlagLabel(call.success)}
                            {" | "}fallback {runtimeFlagLabel(call.fallback_used)}
                            {" | "}error {call.error_code ?? "-"}
                          </p>
                        ),
                      )}
                    </div>
                  )}
                </article>
              </div>
              <article className="row-card">
                <h3>Candidate task ledger</h3>
                <p>
                  This ledger shows candidate-level fetch, extract, and evaluate
                  execution as durable task evidence rather than only as run-level
                  summary counts.
                </p>
                {candidateTasks?.status === "loading" && (
                  <p>Loading candidate task ledger...</p>
                )}
                {candidateTasks?.status === "error" && (
                  <p className="error">{candidateTasks.message}</p>
                )}
                {candidateTasks?.status === "ready" &&
                  candidateTaskItems.length === 0 && (
                    <p>No candidate task records found.</p>
                  )}
                {candidateTasks?.status === "ready" &&
                  candidateTaskItems.map((task) => (
                    <article className="ledger-item" key={task.task_id}>
                      <p>
                        {task.stage} | {task.status} | candidate {task.candidate_id}
                      </p>
                      <p>
                        attempt {task.attempt ?? 0}/{task.max_attempts ?? 0}
                        {task.depends_on_task_ids &&
                        task.depends_on_task_ids.length > 0
                          ? ` | depends on ${task.depends_on_task_ids.join(", ")}`
                          : ""}
                      </p>
                      <pre>{compactJson(task.output_ref ?? {})}</pre>
                    </article>
                  ))}
              </article>
              <pre>{compactJson(run.data.errors ?? [])}</pre>
            </div>
          )}
        </section>

        <section className="panel">
          <h2>Trace Timeline</h2>
          <p className="panel-copy">
            Trace and governance events make the monitor flow explainable: source
            planning, retrieval, extraction, evaluation, and worker handling all
            leave visible records.
          </p>
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
