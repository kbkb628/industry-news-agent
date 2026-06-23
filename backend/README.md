# Industry News Agent

## Scope

This backend implements the core industry-news monitoring project described in
`DEVELOPMENT_GUIDE.md`, centered on a working end-to-end monitor loop plus a set
of already completed optional integrations that remain truthful in scope.

For a concise resume-to-code evidence map and claim status labels, see
[`../docs/resume-alignment.md`](../docs/resume-alignment.md). Repository
milestone tracking lives in [`../PROJECT_TODO.md`](../PROJECT_TODO.md).

The core runtime is now a real in-process multi-agent monitor architecture:

```text
supervisor_bootstrap
  -> planner_agent
  -> retrieval_agent
  -> extraction_agent
  -> evaluation_agent
  -> supervisor_finalize
```

The supervisor owns run lifecycle and final persistence. Specialist agents
collaborate through explicit shared-state contracts and then mirror compatible
fields back into the legacy API-facing run snapshot.

Durable storage contract:

- PostgreSQL is the runtime durable source of truth for topics, monitor runs,
  candidates, extracted items, decisions, push records, run events, and eval
  results.
- Redis owns short-lived coordination only: queue transport, active-run
  protection, and transient worker execution state. Redis and Redis Stream do
  not replace PostgreSQL business facts.
- If Redis is unavailable, runtime coordination may degrade to in-memory
  execution, but PostgreSQL business facts remain durable and authoritative.
- OpenSearch/Elasticsearch is a derived retrieval projection of persisted
  records, not an authoritative store.

Included in the current codebase:

- topic creation, listing, and detail APIs
- MockLLM-backed LangGraph monitor workflow with real supervisor/specialist
  agent separation
- persisted monitor runs, push records, run events, and eval results
- persisted candidate, extracted item, and structured decision records for monitor runs with snapshot fallback
- richer eval metrics for raw-summary, browser fallback, and provider fallback trends
- minimal HTML admin pages for topics, pushes, run detail, and events
- local React + Vite dashboard over existing backend APIs
- APScheduler topic jobs that enqueue worker runs
- Redis-backed run queue with in-memory fallback
- Redis Stream consumer-group flow for queued monitor runs
- worker retry, timeout, active-run guard, and governance events
- optional OneSearch-compatible MCP gateway boundary for `search_news`
- optional OpenWebSearch provider path with mock search fallback
- explicit browser fetch fallback metadata and events
- optional Playwright MCP-compatible browser fetch provider behind the HTTP fallback path
- optional OpenSearch-compatible candidate history full-text index projection
- optional deterministic local semantic-like dedup after exact dedup
- optional generic webhook notification channel after persisted push records
- deterministic MockEvalJudge adapter for the LLM-as-Judge evaluation contract
- optional OpenAI-compatible LLM-as-Judge provider with mock fallback
- local Docker Compose stack for backend, PostgreSQL, and Redis

## Current Architecture

### Agent Stages

- `supervisor_bootstrap`
- `planner_agent`
- `retrieval_agent`
- `extraction_agent`
- `evaluation_agent`
- `supervisor_finalize`

### Shared State Contracts

The multi-agent pipeline exchanges explicit state sections:

- `run_context`
- `business_memory`
- `planner_output`
- `retrieval_output`
- `extraction_output`
- `evaluation_output`

These structured sections let the planner, retrieval, extraction, and
evaluation stages collaborate without depending on each other's internal
implementation details.

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

Redis Stream is used when Redis is available. The code falls back to an
in-memory queue only as an execution fallback, not as the source of truth for
business records. Governance events keep the coordination backend visible in
persisted run traces while PostgreSQL remains the authoritative record of run
facts.

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
boundary, not a claim of verified live MCP service deployment.

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
as complete article content.

Optional history-index variables:

- `HISTORY_INDEX_PROVIDER=none` keeps the external history index disabled.
- `HISTORY_INDEX_PROVIDER=opensearch` enables the optional OpenSearch-compatible
  candidate history full-text projection when `OPENSEARCH_BASE_URL` is configured.
- `OPENSEARCH_BASE_URL` points at an OpenSearch/Elasticsearch-compatible HTTP
  service root.
- `OPENSEARCH_INDEX_NAME` defaults to `industry-news-candidates`.
- `OPENSEARCH_TIMEOUT_SECONDS` defaults to `10.0`.

The history index is a projection of persisted candidate records during final
evaluation as the monitor run completes. PostgreSQL remains the source of truth.
Index failures are recorded as run events/errors and do not masquerade as
successful indexing. This does not implement a vector database or external
embedding pipeline.

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
back persisted push records. The current implementation does not provide a
production notification retry queue.

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
- `GET /api/pushes`
- `GET /api/topics/{topic_id}/pushes`
- `GET /api/monitor/runs/{run_id}/events`
- `POST /api/eval/run`
- `GET /api/eval/summary`

`GET /api/monitor/runs/{run_id}` currently returns the compatibility snapshot,
not the full structured multi-agent contract surface.

## Minimal HTML Pages

- `GET /`
- `GET /pushes`
- `GET /quality`
- `GET /runs/{run_id}`
- `GET /runs/{run_id}/events`
