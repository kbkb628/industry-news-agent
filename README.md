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
- `Supervisor -> Planner -> Retrieval -> Extraction -> Evaluation` stage flow
- structured shared-state contracts plus compatibility mirror fields
- PostgreSQL persistence for topics, runs, candidates, push records, events,
  and eval results
- Redis-backed queued execution with in-memory fallback
- APScheduler topic registration and worker consumption flow
- MockLLM-first execution path with replaceable provider boundaries
- local JSONL/keyword-based business context retrieval
- visible fallback, error, and governance events

## Multi-Agent Architecture

The monitor flow is organized around a supervisor and specialist agents rather
than a flat list of helper functions.

```text
supervisor_bootstrap
  -> planner_agent
  -> retrieval_agent
  -> extraction_agent
  -> evaluation_agent
  -> supervisor_finalize
```

Specialist agents collaborate through explicit shared-state sections:

- `run_context`
- `business_memory`
- `planner_output`
- `retrieval_output`
- `extraction_output`
- `evaluation_output`

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
-> extraction fetches content and structured evidence
-> evaluation deduplicates, scores, and decides push
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

Optional integration boundaries already reserved in code:

- OneSearch-compatible MCP gateway for `search_news`
- OpenWebSearch-compatible provider path
- Playwright MCP-compatible browser fallback path
- OpenSearch-compatible history index projection
- OpenAI-compatible eval judge provider
- generic webhook notification delivery

These integration boundaries are implemented as optional adapters. They should
not be described as verified production deployments unless they are actually
wired to live services in the target environment.

## Quick Start

### Docker Compose

```bash
docker compose up --build
```

Then open:

- `http://localhost:8000/`
- `http://localhost:8000/docs`
- `http://localhost:8000/health`
- `http://localhost:5173`

### Manual Backend

```bash
cd backend
py -3.12 -m pip install -e ".[dev]"
py -3.12 -m uvicorn app.main:app --reload
```

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
- `GET /api/monitor/runs/{run_id}/events`
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
