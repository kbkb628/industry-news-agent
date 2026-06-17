# Industry News Agent MVP

## Scope

This backend implements the `DEVELOPMENT_GUIDE.md` MVP closed loop and the
current Phase 2 scheduler, worker, governance, and real search-provider
extension slices.

Included in the current codebase:

- topic creation, listing, and detail APIs
- MockLLM-backed monitor workflow through LangGraph
- persisted monitor runs, push records, run events, and eval results
- persisted candidate, extracted item, and structured decision records for monitor runs with snapshot fallback
- minimal HTML admin pages for topics, pushes, run detail, and events
- APScheduler topic jobs that enqueue worker runs
- Redis-backed run queue with in-memory fallback
- worker retry, timeout, active-run guard, and governance events
- optional OpenWebSearch provider path with mock search fallback
- explicit browser fetch fallback metadata and events

Not claimed by the current implementation:

- Redis Stream worker groups
- Playwright MCP execution as a live external browser service
- Elasticsearch or vector retrieval
- embedding indexing
- LLM-as-Judge evaluation
- production deployment hardening

## Environment

Runtime dependencies:

- Python 3.11+
- PostgreSQL
- Redis

Required environment variables:

- `DATABASE_URL`
- `REDIS_URL`

Optional Phase 2 search-provider variables:

- `SEARCH_PROVIDER=mock` keeps the deterministic local `mock_search` path.
- `SEARCH_PROVIDER=open_websearch` enables the `search_news` tool when
  `OPEN_WEBSEARCH_BASE_URL` is also configured.
- `OPEN_WEBSEARCH_BASE_URL` points at an OpenWebSearch-compatible HTTP service.
- `OPEN_WEBSEARCH_TIMEOUT_SECONDS` defaults to `10.0`.

Example `.env`:

```env
DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/news_agent
REDIS_URL=redis://localhost:6379/0
SEARCH_PROVIDER=mock
# SEARCH_PROVIDER=open_websearch
# OPEN_WEBSEARCH_BASE_URL=http://localhost:8080
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

## Test

```bash
cd backend
py -3.12 -m pytest -v
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

## Minimal HTML Pages

- `GET /`
- `GET /pushes`
- `GET /runs/{run_id}`
- `GET /runs/{run_id}/events`
