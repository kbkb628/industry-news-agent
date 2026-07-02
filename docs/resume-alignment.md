# Resume Alignment Evidence Map

This document maps the resume-facing claims for the industry-news structured
push agent to the implemented code, exposed APIs, visible pages, and current
truth boundary. The labels below are intentionally conservative:

- `ready` means the claim is already supported by code and user-visible flows.
- `partial` means the core capability exists, but the wording should stay
  scoped to the implemented boundary.
- `boundary` means the repo contains an integration hook or compatibility shim,
  not a verified live production deployment.
Adapter code alone does not imply a live service or enabled provider in the target runtime.

Final verification status for this document:

- backend broad verification passed on July 1, 2026:
  `py -3.12 -m pytest backend/tests/test_demo_bootstrap.py backend/tests/test_tools_and_eval.py backend/tests/test_monitor_run_flow.py backend/tests/test_topics_api.py -q`
- frontend verification passed on July 1, 2026:
  `npm --prefix frontend test -- --run`
  `npm --prefix frontend run build`
- repository hygiene check on July 1, 2026:
  `git diff --check`
  `git status --short` showed expected local modifications pending commit

## Resume Claim Snapshot

The project can truthfully be described as a topic-driven industry-news push
agent with:

- a real in-process multi-agent monitor flow
- candidate-level task orchestration inside that monitor flow
- structured planner, retrieval, extraction, and evaluation stages
- scheduler and worker governance with bounded concurrency, retry, timeout, and
  active-run controls
- persisted run history, push decisions, candidate records, candidate task
  ledger records, and eval results
- a unified tool-access contract read surface with visible per-capability
  provider paths plus compact per-call access evidence
- optional provider boundaries for search, browser fetch, history indexing,
  judge scoring, and notification delivery

## Claim To Code Evidence

### 1. "Built a real in-process multi-agent architecture"

- Status: `ready`
- Code:
  - `backend/app/agent/graph.py`
  - `backend/app/agent/nodes.py`
  - `backend/app/agent/candidate_orchestrator.py`
  - `backend/app/agent/contracts.py`
  - `backend/app/agent/state.py`
- Evidence:
  - the graph is organized into `supervisor_bootstrap -> planner_agent ->
    retrieval_agent -> candidate_task_orchestrator -> supervisor_finalize`
  - `candidate_task_orchestrator` schedules bounded per-candidate fetch,
    extract, and evaluate work while keeping LangGraph as the top-level backbone
  - stage outputs are carried in structured sections such as
    `business_memory`, `planner_output`, `retrieval_output`,
    `extraction_output`, and `evaluation_output`
  - per-candidate orchestration evidence is persisted through the candidate task
    ledger and exposed by API
  - compatibility mirror fields still exist for the current API snapshot
- API / pages:
  - `POST /api/monitor/{topic_id}/run`
  - `GET /api/monitor/runs/{run_id}`
  - `GET /api/monitor/runs/{run_id}/candidate-tasks`
  - `GET /runs/{run_id}`
- Truth boundary:
  - this is an in-process LangGraph orchestration model, not distributed agent
    execution

### 2. "PlannerAgent reasons over topic, business memory, and LLM-expanded keywords"

- Status: `ready`
- Code:
  - `backend/app/agent/planner_agent.py`
  - `backend/app/agent/planner.py`
  - `backend/app/llm/base.py`
- Evidence:
  - `PlannerAgent.run(state)` reads `topic` and `business_memory`
  - it expands keywords via the existing LLM interface
  - it builds structured `query_plan`, `source_plan`,
    `retrieval_strategy`, and `planning_reasons`
  - legacy top-level `expanded_queries` and `source_plan` are still mirrored for
    compatibility
- API / pages:
  - `GET /api/monitor/runs/{run_id}`
  - `GET /runs/{run_id}`
  - local React dashboard run detail view
- Truth boundary:
  - planning is structured and context-aware, but remains bounded by the
    current mock/adapter LLM and the implemented source options

### 3. "Implemented candidate retrieval, browser fallback, and evidence extraction"

- Status: `ready`
- Code:
  - `backend/app/agent/retrieval_agent.py`
  - `backend/app/agent/extraction_agent.py`
  - `backend/app/tools/search_tool.py`
  - `backend/app/tools/browser_fetch_tool.py`
  - `backend/app/tools/rss_tool.py`
- Evidence:
  - retrieval consumes planner output and produces a candidate pool
  - extraction fetches article content and records browser fallback metadata
  - tool registry wires both mock and optional provider-backed boundaries
- API / pages:
  - `GET /api/monitor/runs/{run_id}/candidates`
  - `GET /runs/{run_id}`
- Truth boundary:
  - optional browser and search integrations are real adapters, but they are
    only truthful to describe as boundaries unless the target environment
    proves the live service is configured

### 4. "Added evaluation, push decisioning, and quality metrics"

- Status: `ready`
- Code:
  - `backend/app/agent/evaluation_agent.py`
  - `backend/app/eval/rule_scorer.py`
  - `backend/app/eval/judge.py`
  - `backend/app/tools/push_tool.py`
- Evidence:
  - evaluation deduplicates, scores, decides push/skip, and writes
    `eval_result`
- the judge layer supports the mock rule judge and an optional
  OpenAI-compatible boundary
- persisted eval history now includes recall proxy, false-positive proxy,
  candidate-task failure-rate proxy, event-latency proxy, and runtime-cost proxy
- run detail surfaces now read back judge runtime explicitly with configured
  provider, effective mode, fallback flag, and issue count, so the judge
  boundary is visible at run level instead of only through raw eval payloads
  - push decisions are persisted and exposed through run snapshots
- API / pages:
  - `POST /api/eval/run`
  - `GET /api/eval/summary`
  - `GET /pushes`
  - `GET /quality`
  - `GET /runs/{run_id}`
  - local React dashboard run detail view
- Truth boundary:
- the current judge default is deterministic and local; live judge support is
  optional and should be described as a provider boundary
- recall, false-positive, failure-rate, latency, and runtime-cost metrics are
  truthful as proxy evidence surfaces, not as production monitoring or
  real-time SLO claims

### 5. "Built scheduler and worker governance around the monitor loop"

- Status: `ready`
- Code:
  - `backend/app/scheduler/worker.py`
  - `backend/app/api/monitor.py`
  - `backend/app/agent/nodes.py`
- Evidence:
- worker execution includes bounded concurrency, retry, timeout, and active-run
  guard behavior
  - scheduled topic jobs enqueue monitor runs
  - governance events are emitted for the run lifecycle
- API / pages:
  - `GET /api/monitor/runs/{run_id}/events`
  - `GET /runs/{run_id}/events`
- Truth boundary:
  - this is a real scheduler/worker flow, not a production-grade orchestration
    platform

### 6. "Persisted runs, pushes, and traceable quality history"

- Status: `ready`
- Code:
  - `backend/app/storage/models.py`
  - `backend/app/storage/repository.py`
  - `backend/app/api/monitor.py`
  - `backend/app/api/pushes.py`
  - `backend/app/api/candidates.py`
  - `backend/app/api/events.py`
- Evidence:
  - monitor runs, candidates, extracted items, decisions, pushes, and eval
    results are persisted
  - candidate task ledger records are persisted for per-candidate runtime
    readback
  - the public APIs expose run detail, push history, candidate detail, and
    event traces
- API / pages:
  - `GET /api/monitor/runs/{run_id}`
  - `GET /api/monitor/runs/{run_id}/candidates`
  - `GET /api/monitor/runs/{run_id}/candidate-tasks`
  - `GET /api/monitor/runs/{run_id}/events`
  - `GET /api/pushes`
  - `GET /api/topics/{topic_id}/pushes`
  - `GET /`
  - `GET /pushes`
  - `GET /quality`
  - `GET /runs/{run_id}`
- Truth boundary:
  - the compatibility snapshot remains the primary read surface for existing UI
    paths
  - quality pages and dashboard cards now expose the persisted proxy metrics
    explicitly so the resume wording stays inside the actual runtime evidence

### 7. "Unified search/browser/notification access under one contract"

- Status: `ready`
- Code:
  - `backend/app/mcp/gateway.py`
  - `backend/app/mcp/local_gateway.py`
  - `backend/app/mcp/onesearch_gateway.py`
  - `backend/app/integrations/runtime_summary.py`
  - `backend/app/tools/registry.py`
  - `backend/app/templates/run_detail.html`
  - `frontend/src/App.tsx`
- Evidence:
  - `integration_runtime.tool_access.contract` is now a stable
    `unified_tool_gateway` read surface
  - the `tool_access` summary is now sourced from the gateway layer itself via
    `ToolGateway.describe_tool_access()`, so the unified contract is backed by
    the real execution entry point rather than only by settings-time inference
  - search, browser, and notification each expose both `tool_name` and
    `provider_path`
  - gateway-owned `ToolResponse.metadata.access` now stamps the same unified
    contract at call time for search, browser, and notification, so the runtime
    evidence is not limited to a display-only summary layer
  - `integration_runtime.tool_access.calls` exposes a compact per-call access
    ledger with capability, provider path, provider, success/failure, fallback,
    and error-code evidence for the actual run
  - run-detail HTML and dashboard surfaces also expose notification runtime
    separately from the tool-access summary, so delivery-path evidence is not
    hidden behind the generic contract section
  - the dashboard run-detail surface now also exposes browser attempt counts,
    blocked-domain counts, last browser provider, notification delivery-attempt
    state, and notification failure code for tighter degradation readback
  - the dashboard and HTML run detail page show the contract separately from
    the actual provider path used by that capability, while also surfacing the
    compact call ledger for concrete run-level readback
- API / pages:
  - `GET /api/monitor/runs/{run_id}`
  - `GET /runs/{run_id}`
- Truth boundary:
  - the contract is unified, but the actual provider paths are not all MCP in
    the current repo
  - search may run through `mcp_gateway`; browser and notification currently
    remain on `tool_gateway` with optional provider-backed adapters behind
    those local tool boundaries

### 8. "Supports optional integrations without pretending they are always live"

- Status: `boundary`
- Code:
  - `backend/app/tools/registry.py`
  - `backend/app/mcp/onesearch_gateway.py`
  - `backend/app/search/history_index.py`
  - `backend/app/tools/semantic_dedup.py`
  - `backend/app/tools/notification_tool.py`
  - `backend/app/tools/browser_fetch_tool.py`
  - `backend/app/eval/judge.py`
- Evidence:
  - OneSearch-compatible search gateway
  - OpenWebSearch-compatible search provider
  - Playwright MCP-compatible browser fetch fallback
  - OpenSearch-compatible history projection and query path
  - local semantic dedup
  - webhook notification delivery
  - OpenAI-compatible judge provider
- API / pages:
  - `GET /api/history/search`
  - `GET /history-search`
  - the same monitor and eval endpoints expose the resulting metadata when the
    adapters are configured
- Truth boundary:
  - these are optional boundaries and fallback paths, not guaranteed live
    deployments

## Ready To Say In Interview

Use these phrasings when you want to stay close to the implementation:

- "Built a topic-driven, in-process multi-agent monitor flow with supervisor
  orchestration, candidate-level task scheduling, and structured stage
  contracts."
- "PlannerAgent expands keywords from business memory and turns them into a
  structured query and source plan."
- "The system persists runs, candidate records, push decisions, and eval
  results, and surfaces them through APIs and admin pages."
- "Candidate fetch, extract, and evaluate work is recorded as a task ledger so
  orchestration evidence is queryable after the run finishes."
- "I added scheduler and worker governance so queued runs have bounded
  concurrency, retry, timeout, and active-run controls."
- "I used a unified tool-access contract for search, browser, and notification,
  while surfacing the actual provider path per capability and compact per-call
  access evidence so the MCP boundary stays truthful."

## Partial / Boundary Claims

Keep these scoped unless the runtime environment proves more:

- "LLM-backed" should be read as `MockLLM` plus swappable provider boundaries
  unless a live provider is actually configured.
- "RAG grounding" is now visible through run-detail read surfaces, but it is a
  local JSONL + keyword/BM25/hashed-embedding path rather than an external
  vector-store deployment.
- "Search integration" should be framed as a unified tool contract plus an
  optional provider boundary.
- "Browser automation" should be framed as a fallback adapter, not a fully
  managed browser fleet.
- "OpenSearch history index" should be framed as a projection boundary, not the
  source of truth, even though the current repo now exposes a real queryable
  read surface for that projection.
- "AI judge" should be framed as a deterministic local judge with an optional
  OpenAI-compatible adapter.
- "Resilience" should be framed as bounded concurrency, retry, timeout, and
  active-run controls rather than a distributed worker fleet or full
  circuit-breaker system.

## Suggested Demo Order

1. Start at `GET /`
2. Open `GET /runs/{run_id}` to show the compatibility snapshot
3. Open `GET /api/monitor/runs/{run_id}/candidate-tasks` to show candidate task
   orchestration evidence
4. Open `GET /runs/{run_id}/events` to show trace and governance events
5. Open `GET /pushes` and `GET /quality` to show the persisted output and
   evaluation signals, including recall proxy, task-failure proxy, and latency
   proxy
6. Reference `POST /api/monitor/{topic_id}/run`, `GET /api/monitor/runs/{run_id}`,
   and `GET /api/monitor/runs/{run_id}/candidate-tasks`
   to tie the UI back to the API
