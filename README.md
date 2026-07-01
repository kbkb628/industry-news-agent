# Industry News Structured Push Agent

This repository contains a full project showcase for the industry-news
structured push agent described by `DEVELOPMENT_GUIDE.md`.

The system is not a generic crawler and not a simple RSS summarizer. It is a
topic-driven monitoring system that plans retrieval, gathers candidate news,
extracts structured evidence, evaluates business value, records push decisions,
and keeps traceable run history.

## Current Implementation

The current codebase already runs a truthful end-to-end closed loop with:

- FastAPI backend APIs and Swagger
- minimal server-rendered HTML admin pages
- local React + Vite dashboard for read-only operations view
- LangGraph-based in-process multi-agent orchestration
- `Supervisor -> Planner -> Retrieval -> CandidateTaskOrchestrator -> Finalize`
  top-level flow
- candidate-level fetch / extract / evaluate task orchestration inside the
  monitor run
- structured shared-state contracts plus compatibility mirror fields
- PostgreSQL persistence for topics, runs, candidates, push records, events,
  and eval results
- Redis-backed queued execution with in-memory fallback
- APScheduler topic registration and worker consumption flow
- MockLLM-first execution path with replaceable provider boundaries
- local JSONL/keyword-based business context retrieval
- explicit run-detail readback for local RAG grounding and guidance metrics
- persisted quality proxy evidence for recall, false-positive, task-failure,
  event-latency, and runtime-cost readback
- visible fallback, error, and governance events

## Multi-Agent Architecture

The monitor flow is organized around a supervisor and specialist agents rather
than a flat list of helper functions.

```text
supervisor_bootstrap
  -> planner_agent
  -> retrieval_agent
  -> candidate_task_orchestrator
  -> supervisor_finalize
```

Specialist agents collaborate through explicit shared-state sections:

- `run_context`
- `business_memory`
- `planner_output`
- `retrieval_output`
- `extraction_output`
- `evaluation_output`

Candidate-level execution is now expressed as bounded task orchestration inside
the graph rather than as separate top-level extraction/evaluation graph nodes.
Fetch, extract, and evaluate still remain real specialist behaviors, but they
run under `candidate_task_orchestrator` so the system can show per-candidate
task evidence and controlled same-stage coordination.

For a claim-by-claim mapping from the resume wording to real code, APIs, pages,
and truth boundaries, see [`docs/resume-alignment.md`](docs/resume-alignment.md).
Current milestone status lives in [`PROJECT_TODO.md`](PROJECT_TODO.md).

For API stability, the finalization stage mirrors key values back into legacy
top-level fields such as `expanded_queries`, `candidate_items`,
`final_decisions`, and `eval_result`.

## Closed Loop

The implemented loop is:

```text
create topic
-> enqueue or manually trigger run
-> planner expands queries and plans sources
-> retrieval gathers candidate pool
-> candidate_task_orchestrator runs fetch / extract / evaluate tasks per candidate
-> global evaluation view deduplicates, scores, and decides push
-> supervisor persists records, trace events, and eval output
-> dashboard / HTML / APIs expose run results
```

## Truthful Scope Boundary

Implemented now:

- real run persistence and event tracing
- real candidate pool management
- real dedup / scoring / push-decision path
- real scheduler + queued worker flow
- real compatibility-preserving multi-agent contracts
- real unified tool-access contract readback for search, browser, and
  notification with per-capability provider-path evidence

Optional integration boundaries already reserved in code:

- OneSearch-compatible MCP-backed provider path for `search_news`
- OpenWebSearch-compatible provider path
- Playwright-compatible browser fallback adapter boundary
- OpenSearch-compatible history index projection boundary
- OpenAI-compatible eval judge provider
- generic webhook notification delivery

These integration boundaries are implemented as optional adapters. They should
not be described as verified production deployments unless they are actually
wired to live services in the target environment.

## Final Alignment Status

The repository is now aligned to the resume-facing technical wording inside the
actual runtime boundary of this codebase:

- multi-agent orchestration is real and runs in-process through LangGraph
- candidate-level task coordination is real and leaves durable task-ledger evidence
- Redis owns short-lived queue and retry coordination while PostgreSQL remains
  the durable business store
- RAG uses local keyword + BM25 + hashed-embedding retrieval instead of
  embedding-like naming over token overlap alone
- quality pages and dashboard surfaces expose persisted proxy evidence,
  including event-latency and runtime-cost proxies, rather than only aggregate
  success counters

What remains intentionally scoped:

- external search / browser / judge / notification providers are optional
  boundaries, not guaranteed live services
- quality metrics are proxy evidence for the local runtime, not production SLOs
- queue and candidate-stage reliability are implemented as bounded concurrency,
  retry, timeout, and active-run controls rather than as a distributed
  circuit-breaker fleet
- the project is a truthful showcase system, not a production deployment claim

## Quick Start

### Docker Compose

```bash
docker compose up --build
```

Then open:

- `http://localhost:8000/`
- `http://localhost:8000/docs`
- `http://localhost:8000/health`
- `http://localhost:8000/history-search`
- `http://localhost:5173`

### Manual Backend

```bash
cd backend
py -3.12 -m pip install -e ".[dev]"
py -3.12 -m uvicorn app.main:app --reload
```

### Deterministic Demo Bootstrap

Use the demo bootstrap after the backend stack is available when you want a
fresh environment to show the same persisted evidence chain without depending
on old local database history.

It uses the normal backend settings contract, so `DATABASE_URL` and
`REDIS_URL` must already be configured through `backend/.env`, exported
environment variables, or the Docker Compose environment.

```bash
cd backend
py -3.12 -m app.demo.bootstrap_cli
```

The bootstrap path is intentionally bounded:

- it creates or reuses the fixed demo topic `topic_ai_agent`
- it resets the fixed demo run `run_demo_bootstrap`
- it synchronously runs the real LangGraph monitor flow with `MockLLM`
- it uses the existing fixture-backed RSS/search/content tools
- it persists the resulting run, candidates, candidate tasks, pushes, events,
  and eval output through the normal repository layer

This is a deterministic local showcase helper, not a production ingestion mode.
It exists so the HTML pages and dashboard can be reproduced from an empty local
database with truthful runtime artifacts.

After running it, the main demo readback order is:

1. `GET /`
2. `GET /runs/run_demo_bootstrap`
3. explain the `RAG grounding runtime` section on the run detail page
4. `GET /runs/run_demo_bootstrap/events`
5. `GET /pushes`
6. `GET /quality`
7. `GET /history-search`

The quality surfaces now expose persisted proxy evidence in addition to the
existing success and fallback counts:

- recall proxy from retrieved-to-deduped candidate retention
- false-positive proxy totals from high-score-but-rejected noisy candidates
- candidate task failure-rate proxy across fetch/extract/evaluate ledger records
- event-latency proxy from recorded graph and worker events
- runtime-cost proxy units from tool calls, browser fallbacks, and judge/model decisions

These are intentionally described as proxy signals for the local/runtime-real
MVP, not as production observability or online serving SLAs.

### Manual Frontend

```bash
cd frontend
npm install
npm run dev
```

## Main APIs

- `POST /api/topics`
- `GET /api/topics`
- `GET /api/topics/{topic_id}`
- `POST /api/monitor/{topic_id}/run`
- `GET /api/monitor/runs/{run_id}`
- `GET /api/monitor/runs/{run_id}/candidates`
- `GET /api/monitor/runs/{run_id}/candidate-tasks`
- `GET /api/monitor/runs/{run_id}/events`
- `GET /api/history/search`
- `GET /api/pushes`
- `GET /api/topics/{topic_id}/pushes`
- `POST /api/eval/run`
- `GET /api/eval/summary`

## Repository Layout

```text
backend/   FastAPI APIs, agent graph, tools, storage, scheduler, tests
frontend/  React + Vite read-only management dashboard
docs/      frozen specs and implementation plans for major milestones
```

## Verification

Backend verification:

```bash
cd backend
py -3.12 -m pytest -q
```

Frontend verification:

```bash
cd frontend
npm test -- --run
npm run build
```

For backend-specific environment details and optional integration variables, see
[`backend/README.md`](backend/README.md).
