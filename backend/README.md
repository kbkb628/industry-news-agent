# Industry News Agent MVP

## Scope

This backend implements the `DEVELOPMENT_GUIDE.md` MVP closed loop only.

Included in the current codebase:

- topic creation, listing, and detail APIs
- MockLLM-backed monitor workflow through LangGraph
- persisted monitor runs, push records, run events, and eval results
- minimal HTML admin pages for topics, pushes, run detail, and events
- scheduler bootstrap only

Not claimed by this MVP:

- Redis Streams workers
- Playwright MCP execution
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

Example `.env`:

```env
DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/news_agent
REDIS_URL=redis://localhost:6379/0
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
