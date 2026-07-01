# Industry News Agent

## Scope

This backend implements the core industry-news monitoring project described in
`DEVELOPMENT_GUIDE.md`, centered on a working end-to-end monitor loop plus a set
of optional integration boundaries that remain truthful in scope.

For a concise resume-to-code evidence map and claim status labels, see
[`../docs/resume-alignment.md`](../docs/resume-alignment.md). Repository
milestone tracking lives in [`../PROJECT_TODO.md`](../PROJECT_TODO.md).

The core runtime is now a real in-process multi-agent monitor architecture:

```text
supervisor_bootstrap
  -> planner_agent
  -> retrieval_agent
  -> candidate_task_orchestrator
  -> supervisor_finalize
```

The supervisor owns run lifecycle and final persistence. Specialist agents
collaborate through explicit shared-state contracts and then mirror compatible
fields back into the legacy API-facing run snapshot.

Durable storage contract:

- PostgreSQL is the runtime durable source of truth for topics, monitor runs,
  candidates, extracted items, decisions, push records, run events, and eval
  results.
- Redis and Redis Stream do not replace PostgreSQL business facts.
- Redis owns short-lived coordination only: queue transport, active-run
  protection, enqueue dedup, retry visibility, and transient worker execution
  state.
- If Redis is unavailable, runtime coordination may degrade to in-memory
  execution, but PostgreSQL business facts remain durable and authoritative.
- OpenSearch/Elasticsearch is a derived retrieval projection only, not an
  authoritative store.

Included in the current codebase:

- topic creation, listing, and detail APIs
- MockLLM-backed LangGraph monitor workflow with real supervisor/specialist
  agent separation
- persisted monitor runs, push records, run events, and eval results
- persisted candidate, extracted item, and structured decision records for monitor runs with snapshot fallback
- richer eval metrics for raw-summary, browser fallback, and provider fallback trends
- minimal HTML admin pages for topics, pushes, run detail, and events
- minimal HTML admin pages for topics, pushes, quality, history search, run detail, and events
- explicit run-detail and resume-alignment read surfaces for local RAG grounding evidence
- local React + Vite dashboard over existing backend APIs
- APScheduler topic jobs that enqueue worker runs
- Redis-backed run queue with in-memory fallback
- Redis Stream consumer-group flow for queued monitor runs with explicit post-processing acknowledge/requeue semantics
- worker retry, timeout, active-run guard, and governance events
- optional OneSearch-compatible MCP-backed provider path for `search_news`
- optional OpenWebSearch provider path with mock search fallback
- explicit browser fetch fallback metadata and events
- optional Playwright-compatible browser fetch adapter behind the HTTP fallback path
- optional OpenSearch-compatible candidate history full-text index projection
- optional deterministic local semantic-like dedup after exact dedup
- optional generic webhook notification channel after persisted push records
- deterministic MockEvalJudge adapter for the LLM-as-Judge evaluation contract
- optional OpenAI-compatible LLM-as-Judge provider with mock fallback
- local Docker Compose stack for backend, PostgreSQL, and Redis

Final resume-truth alignment status:

- the multi-agent, scheduler/worker, Redis coordination, RAG retrieval, and
  quality-evidence claims are now all backed by implemented runtime behavior
- `integration_runtime.tool_access` now separates the unified tool-access
  contract from the actual provider path used by each capability
- the optional provider-facing pieces remain explicit integration boundaries
  whose truth depends on environment configuration, not on repository presence
- the quality metrics exposed by `GET /api/eval/summary`, `GET /quality`, and
  the React dashboard are persisted proxy signals rather than production
  observability guarantees

## Current Architecture

### Top-Level Graph

- `supervisor_bootstrap`
- `planner_agent`
- `retrieval_agent`
- `candidate_task_orchestrator`
- `supervisor_finalize`

### Shared State Contracts

The multi-agent pipeline exchanges explicit state sections:

- `run_context`
- `business_memory`
- `planner_output`
- `retrieval_output`
- `extraction_output`
- `evaluation_output`

These structured sections let the planner, retrieval, candidate-task fetch,
candidate-task extraction, and candidate-task evaluation behaviors collaborate
without depending on each other's internal implementation details.

`GET /api/monitor/runs/{run_id}` now exposes those structured sections directly,
so planner, retrieval, extraction, and evaluation outputs are first-class API
readback instead of staying only as internal runtime state.

### Compatibility Strategy

Current HTTP run endpoints still expose the legacy snapshot fields required by
the MVP contract, including:

- `expanded_queries`
- `candidate_items`
- `final_decisions`
- `errors`

Those fields are mirrored from the structured multi-agent outputs during
supervisor finalization so existing API responses, HTML pages, and dashboard
screens continue to work while the internals use stronger contracts.

The structured sections are the authoritative runtime contracts. The legacy
snapshot fields remain compatibility mirrors for concise readback and older
demo surfaces.

Candidate-level orchestration now runs inside the LangGraph monitor flow after
retrieval. Fetch, extract, and evaluate still remain real specialist
behaviors, but they are scheduled under `candidate_task_orchestrator` instead
of being modeled as separate top-level graph nodes. The orchestrator now uses
bounded in-process workers per stage, honoring the `candidate_*_concurrency`
settings while still preserving fetch -> extract -> evaluate ordering for each
candidate. Redis/runtime state owns short-lived candidate task coordination,
while PostgreSQL persists candidate task ledger facts, including retry
attempts, for historical readback.
`GET /api/monitor/runs/{run_id}/candidate-tasks` exposes durable task evidence.
This should be described as bounded in-process concurrency with retry/timeout
controls, not as a distributed stage-worker fleet or a full circuit-breaker
implementation.

### Queue And Worker Flow

Manual runs can still be triggered directly through the monitor API, and topic
schedules are registered through APScheduler. Scheduled work is enqueued and
consumed by `MonitorWorkerService`, which provides:

- active-run guard per topic
- queue wait metrics
- worker governance events
- retry and timeout handling
- persisted failed-run closure when execution breaks

APScheduler owns topic-bound cron registration and trigger production. It does
not execute the heavy monitor flow directly; scheduled jobs enqueue work for
worker consumption.

Redis Stream is used when Redis is available. Before reading only new stream
entries, the worker performs a bounded pending-delivery reclaim pass so
abandoned deliveries can be retried by another consumer. Deliveries are not
acknowledged on dequeue; the worker acknowledges only after successful
completion, after an intentional active-run skip, or after a final failed run
has been persisted. Retryable failures are re-enqueued with
`retry_reason=worker_retry` before the original delivery is acknowledged, and
the current worker invocation stops at that handoff point. The queue owns the
next retry delivery, including the durable `run_id` plus persisted
`retry_count` and `max_retries` metadata needed to exhaust the retry budget
across later deliveries and eventually mark the run failed. Short-lived Redis
coordination also holds scheduler enqueue slots per `topic_id + trigger`,
active-run locks per topic, and transient retry state keyed by `run_id` so the
worker/API can expose retry handoff status without moving durable run facts out
of PostgreSQL.
Timeout handling is best-effort in the current in-process thread model. The
worker marks the run failed, records governance timeout events, and blocks late
repository writes from the timed-out invocation path, but it does not guarantee
an OS-level hard stop of arbitrary user code already running inside that thread.
The code falls back to an in-memory queue only as an execution fallback, not as
the source of truth for business records. Governance events keep the
coordination backend visible in persisted run traces while PostgreSQL remains
the authoritative record of run facts.
The current resilience story is bounded concurrency plus retry, timeout,
active-run guard, and transient coordination/rate controls. It should not be
marketed as a distributed worker fleet or a full circuit-breaker subsystem.

`GET /api/monitor/runs/{run_id}` may additionally surface
`run_context.retry_state` when a run is currently parked for worker retry. That
field is intentionally transient: it comes from short-lived coordination state,
not from the durable monitor-run record.

Not claimed by the current implementation:

- general autonomous browsing or a production browser fleet
- verified live OneSearch MCP deployment
- raw MCP protocol session management
- verified Microsoft Playwright MCP live-service deployment
- production Elasticsearch/OpenSearch cluster hardening
- vector database retrieval
- embedding indexing with external model embeddings
- production semantic clustering service
- production notification retry or delivery-queue hardening
- production deployment hardening
- production frontend deployment, authentication, or authorization

The knowledge-base RAG path now uses three local retrieval signals:

- keyword overlap
- BM25 full-text scoring
- local hashed embedding similarity with canonical alias normalization and rerank

This is a real local embedding retrieval path inside the current process, but it
is still intentionally scoped: it does not claim an external embedding service,
vector database, or production embedding indexing pipeline.

## Environment

Runtime dependencies:

- Python 3.11+
- PostgreSQL
- Redis

Required environment variables:

- `DATABASE_URL`
- `REDIS_URL`

Optional MCP gateway variables:

- `MCP_GATEWAY_PROVIDER=local` keeps the default in-process `LocalToolGateway`.
- `MCP_GATEWAY_PROVIDER=onesearch` enables an optional OneSearch-compatible
  gateway boundary only when `ONESEARCH_BASE_URL` is also configured.
- `ONESEARCH_BASE_URL` points at a compatible HTTP wrapper exposing
  `POST /search` with a JSON body of `{"query": "...", "max_results": 10}`.
- `ONESEARCH_TIMEOUT_SECONDS` defaults to `10.0`.
- `ONESEARCH_MAX_RESULTS` defaults to `10`.

The OneSearch path currently applies only to `search_news`. All other tools
remain local/in-process. If the OneSearch provider is unavailable, the runtime
degrades visibly to deterministic local `mock_search` behavior and records the
fallback in tool metadata, run events, and eval metrics. This is an integration
boundary, not a claim of verified live MCP service deployment. When configured,
the run snapshot now exposes `integration_runtime.mcp` so a reviewer can see
whether the MCP-backed path was enabled, actually used, or degraded to
fallback in that specific run.
The same snapshot also exposes `integration_runtime.tool_access`, where
`contract=unified_tool_gateway` stays stable while each capability reports its
actual `provider_path`. In the current repo, search may point at
`mcp_gateway`, while browser and notification still report `tool_gateway`
unless their execution model is changed in code.

Optional search-provider variables:

- `SEARCH_PROVIDER=mock` keeps the deterministic local `mock_search` path.
- `SEARCH_PROVIDER=open_websearch` enables the `search_news` tool when
  `OPEN_WEBSEARCH_BASE_URL` is also configured.
- `OPEN_WEBSEARCH_BASE_URL` points at an OpenWebSearch-compatible HTTP service.
- `OPEN_WEBSEARCH_TIMEOUT_SECONDS` defaults to `10.0`.

Optional eval judge variables:

- `JUDGE_PROVIDER=mock` keeps the deterministic local `MockEvalJudge` path.
- `JUDGE_PROVIDER=openai_compatible` enables live judge calls when
  `JUDGE_BASE_URL` and `JUDGE_API_KEY` are also configured.
- `JUDGE_BASE_URL` points at an OpenAI-compatible `/chat/completions` service root.
- `JUDGE_API_KEY` is sent as the bearer token for the judge provider.
- `JUDGE_MODEL` defaults to `gpt-4o-mini`.
- `JUDGE_TIMEOUT_SECONDS` defaults to `10.0`.

Optional browser fallback variables:

- `BROWSER_FETCH_PROVIDER=none` keeps browser fallback disabled.
- `BROWSER_FETCH_PROVIDER=playwright_mcp` enables the optional
  Playwright MCP-compatible browser fetch provider only when
  `PLAYWRIGHT_MCP_BASE_URL` and `BROWSER_ALLOWED_DOMAINS` are also configured.
- `PLAYWRIGHT_MCP_BASE_URL` points at a compatible HTTP wrapper exposing
  `POST /fetch` with a JSON body of `{"url": "..."}`.
- `PLAYWRIGHT_MCP_TIMEOUT_SECONDS` defaults to `10.0`.
- `BROWSER_ALLOWED_DOMAINS` limits which article domains may use browser fallback.
- `BROWSER_MAX_CONCURRENCY` defaults to `1`; the current fallback path is
  synchronous and does not implement a browser worker pool.
- `BROWSER_MAX_CONTENT_CHARS` defaults to `20000`.

Browser fallback is intentionally last in the fetch chain: fixture/local content
first, plain HTTP second, browser provider only after HTTP failure. Failed browser
fallbacks remain visible as failed candidate fetches instead of being presented
as complete article content. When configured, the run snapshot now exposes
`integration_runtime.browser` so a reviewer can see whether the browser
fallback path was enabled, actually used, and whether degraded browser-backed
attempts occurred in that specific run. The browser runtime section also records
attempt counts, allowed-domain blocks, the last attempted browser provider, and
the visible failure reason when browser fallback could not complete.

Webhook notification delivery is also summarized in
`integration_runtime.notification`, including whether delivery was enabled,
attempted in that run, and whether it succeeded. The snapshot additionally
exposes `integration_runtime.tool_access` so a reviewer can see that all three
capabilities share one readback contract while still showing which ones run
through `mcp_gateway` versus `tool_gateway`.

The `integration_runtime` section is runtime evidence, not a claim that every
environment always wires live external MCP or Playwright-compatible services.
Adapter code alone does not imply a live service or enabled provider in the target runtime.

Optional history-index variables:

- `HISTORY_INDEX_PROVIDER=none` keeps the external history index disabled.
- `HISTORY_INDEX_PROVIDER=opensearch` enables the optional OpenSearch-compatible
  candidate history full-text projection when `OPENSEARCH_BASE_URL` is configured.
- `OPENSEARCH_BASE_URL` points at an OpenSearch/Elasticsearch-compatible HTTP
  service root.
- `OPENSEARCH_INDEX_NAME` defaults to `industry-news-candidates`.
- `OPENSEARCH_TIMEOUT_SECONDS` defaults to `10.0`.

The history index is a derived candidate-history retrieval layer backed by a
projection of persisted candidate records during final evaluation as the monitor
run completes. It supports projection and query, while PostgreSQL remains the
durable source of truth. Index/search failures are recorded as run events/errors
and do not masquerade as successful retrieval capability. This does not
implement a vector database or external embedding pipeline.

The repo now exposes a minimal operator-facing history-search workflow at
`GET /history-search` and `GET /api/history/search`, so the query path is not
just an internal adapter anymore. The provider boundary still stays explicit:
`provider=none` is a truthful outcome when no OpenSearch-compatible service is
configured.

The run detail page and React dashboard also expose the local RAG path more
directly: `business_memory.business_context.semantic_memory` is summarized as
run-level grounding evidence, and evaluation-time guidance metrics are shown
alongside it so the planner/scoring effect chain is visible without reading raw
JSON only.

The same run-detail read surfaces now also summarize
`integration_runtime.notification` directly, so notification delivery no longer
stays implicit behind tool-access or event-only readback.

The dashboard/browser-facing read surface also now shows browser-attempt counts,
blocked-domain counts, last attempted browser provider, notification delivery
attempt state, and notification failure code when present, so degradation
explanations do not depend on raw JSON inspection alone.

Optional semantic-dedup variables:

- `SEMANTIC_DEDUP_PROVIDER=none` keeps the default exact dedup behavior.
- `SEMANTIC_DEDUP_PROVIDER=local` enables deterministic local token-vector
  similarity after exact URL/title/content-fingerprint dedup.
- `SEMANTIC_DEDUP_THRESHOLD` defaults to `0.88`.

The local semantic-like path compares article title, summary, raw summary, and
content tokens with cosine similarity. It keeps the first matching item and
records later near-duplicates in `semantic_dropped_candidate_ids` and
`semantic_drop_reasons`. This is not an external embedding service, vector
database, or production semantic clustering implementation.

Optional notification variables:

- `NOTIFICATION_PROVIDER=none` keeps notification delivery disabled. Push records
  are still persisted and the run records an explicit notification skipped event.
- `NOTIFICATION_PROVIDER=webhook` enables a generic webhook `POST` after push
  records are persisted, when `NOTIFICATION_WEBHOOK_URL` is configured.
- `NOTIFICATION_WEBHOOK_URL` points at the generic webhook endpoint.
- `NOTIFICATION_TIMEOUT_SECONDS` defaults to `10.0`.

Webhook notification failures are recorded in run errors/events and do not roll
back persisted push records. When configured, notification delivery now also
appears in the run snapshot under `integration_runtime.notification` instead of
remaining a side-path visible only in events. The current implementation does
not provide a production notification retry queue.

Example `.env`:

```env
DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/news_agent
REDIS_URL=redis://localhost:6379/0
MCP_GATEWAY_PROVIDER=local
# MCP_GATEWAY_PROVIDER=onesearch
# ONESEARCH_BASE_URL=http://localhost:8090
# ONESEARCH_TIMEOUT_SECONDS=10.0
# ONESEARCH_MAX_RESULTS=10
SEARCH_PROVIDER=mock
# SEARCH_PROVIDER=open_websearch
# OPEN_WEBSEARCH_BASE_URL=http://localhost:8080
JUDGE_PROVIDER=mock
# JUDGE_PROVIDER=openai_compatible
# JUDGE_BASE_URL=https://api.openai.com/v1
# JUDGE_API_KEY=replace-me
BROWSER_FETCH_PROVIDER=none
# BROWSER_FETCH_PROVIDER=playwright_mcp
# PLAYWRIGHT_MCP_BASE_URL=http://localhost:8931
# BROWSER_ALLOWED_DOMAINS='["example.com","news.example.com"]'
HISTORY_INDEX_PROVIDER=none
# HISTORY_INDEX_PROVIDER=opensearch
# OPENSEARCH_BASE_URL=http://localhost:9200
# OPENSEARCH_INDEX_NAME=industry-news-candidates
SEMANTIC_DEDUP_PROVIDER=none
# SEMANTIC_DEDUP_PROVIDER=local
# SEMANTIC_DEDUP_THRESHOLD=0.88
NOTIFICATION_PROVIDER=none
# NOTIFICATION_PROVIDER=webhook
# NOTIFICATION_WEBHOOK_URL=https://hooks.example.com/news
# NOTIFICATION_TIMEOUT_SECONDS=10.0
```

## Install

```bash
cd backend
py -3.12 -m pip install -e ".[dev]"
```

## Run

```bash
cd backend
py -3.12 -m uvicorn app.main:app --reload
```

## Deterministic Demo Bootstrap

For a fresh local database, you can seed one reproducible showcase run without
relying on preexisting history:

The command reads the normal backend settings first, so `DATABASE_URL` and
`REDIS_URL` must already be present in `backend/.env` or the current shell
environment.

```bash
cd backend
py -3.12 -m app.demo.bootstrap_cli
```

This helper:

- creates or reuses the fixed demo topic `topic_ai_agent`
- clears prior persisted artifacts for `run_demo_bootstrap`
- synchronously executes the real monitor graph with `MockLLM`
- uses the existing fixture-backed RSS/search/article content path
- persists run, candidate, extracted item, decision, push, event, eval, and
  candidate-task evidence through the normal repository layer

It is a deterministic local demo path, not a separate product workflow and not
a claim of live external provider execution.

## Run With Docker Compose

The root `docker-compose.yml` is a local demonstration stack, not a production
deployment profile. It starts the backend, local React dashboard, PostgreSQL,
and Redis with mock search enabled:

```bash
docker compose up --build
```

Then open:

- `http://localhost:8000/health`
- `http://localhost:8000/`
- `http://localhost:8000/docs`
- `http://localhost:5173`

## React Dashboard

The `frontend/` app is a local React + Vite management dashboard over existing
backend APIs. It shows topics, push records, run details, trace events, and eval
quality summary data. It does not add authentication, write operations, or
production deployment hardening.

```bash
cd frontend
npm install
npm run dev
```

Then open `http://localhost:5173`.

When using Docker Compose, the local dashboard is available at
`http://localhost:5173` and proxies API calls to the backend service through
`VITE_API_PROXY_TARGET=http://backend:8000`.

## Test

```bash
cd backend
py -3.12 -m pytest -v
```

Frontend verification:

```bash
cd frontend
npm test -- --run
npm run build
```

The automated test suite uses in-memory repository overrides for the monitor
closed loop, so it does not require live PostgreSQL or Redis services to pass.
The runtime application still expects real `DATABASE_URL` and `REDIS_URL`
configuration.

## MVP APIs

- `GET /health`
- `POST /api/topics`
- `GET /api/topics`
- `GET /api/topics/{topic_id}`
- `POST /api/monitor/{topic_id}/run`
- `GET /api/monitor/runs/{run_id}`
- `GET /api/monitor/runs/{run_id}/candidates`
- `GET /api/monitor/runs/{run_id}/candidate-tasks`
- `GET /api/history/search`
- `GET /api/pushes`
- `GET /api/topics/{topic_id}/pushes`
- `GET /api/monitor/runs/{run_id}/events`
- `POST /api/eval/run`
- `GET /api/eval/summary`

`GET /api/monitor/runs/{run_id}` returns both the structured multi-agent stage
sections and the legacy compatibility snapshot mirrors.

## Minimal HTML Pages

- `GET /`
- `GET /pushes`
- `GET /quality`
- `GET /history-search`
- `GET /runs/{run_id}`
- `GET /runs/{run_id}/events`
