# Industry News Agent Phase 2 Status And Roadmap

## Goal

Extend the completed MVP toward the fuller project shape described in
`DEVELOPMENT_GUIDE.md` and the resume entry for "行业资讯结构化推送智能体",
while preserving the working MVP baseline and keeping capability claims truthful.

This document is the current Phase 2 coordination record for branch
`feat/phase2-scheduler-worker`. It replaces the original "next slice is only
Phase 2A" wording, because multiple Phase 2 slices have now been implemented,
verified, committed, and pushed.

## Delivery Strategy

Follow staged delivery. Do not chase the full resume surface area at once. Each
slice must remain:

- optional or default-safe when it depends on external services
- deterministic in tests
- visible through events, errors, metrics, or documentation when degraded
- truthful in README capability claims

Do not claim production hardening, live third-party service verification, vector
database retrieval, external embedding indexing, or provider-specific
notifications unless those capabilities are implemented and verified.

## Completed Phase 2 Slices

### Phase 2A: Scheduler And Worker Execution

Status: implemented.

Evidence:

- `047b312 feat: use redis stream run queue`
- `59a14bf docs: plan redis stream run queue`
- `backend/app/scheduler/jobs.py`
- `backend/app/scheduler/worker.py`
- `backend/tests/test_monitor_run_flow.py`

Implemented scope:

- APScheduler topic jobs enqueue monitor run work.
- Redis Stream queue is used when Redis is reachable.
- In-memory queue fallback remains available when Redis is unavailable.
- Worker consumes queued runs and persists monitor graph results.
- Manual and scheduled triggers remain distinguishable in run state.

### Phase 2B: Concurrency Governance

Status: implemented for bounded worker execution and traceable governance
events.

Evidence:

- `9d9d4b8 feat: persist worker governance events`
- `fe56aa2 fix: accept worker governance events`
- `backend/app/scheduler/worker.py`
- `backend/app/schemas/event_schema.py`
- `backend/tests/test_monitor_run_flow.py`
- `backend/tests/test_supporting_schema_contracts.py`

Implemented scope:

- Active-run guard prevents duplicate topic execution while a run is active.
- Worker timeout handling marks failed runs.
- Worker retry metadata is persisted as governance events.
- Queue wait metrics are persisted in event payloads.
- Event API schema accepts worker governance event types and nodes.

### Phase 2C: Real Tool Integrations

Status: partially implemented with optional, controlled provider paths.

Evidence:

- `d0fd738 feat: add real search provider fallback path`
- `293bb92 feat: add playwright mcp browser fallback`
- `c4b23d2 feat: add opensearch history index adapter`
- `5c687d6 feat: add webhook notification channel`
- `761f902 feat: add onesearch gateway boundary`
- `backend/app/tools/registry.py`
- `backend/app/tools/browser_fetch_tool.py`
- `backend/app/mcp/onesearch_gateway.py`
- `backend/app/search/history_index.py`
- `backend/app/tools/notification_tool.py`
- `backend/README.md`

Implemented scope:

- Optional OneSearch-compatible MCP gateway boundary for `search_news`, with
  explicit configuration and deterministic local fallback.
- Optional OpenWebSearch-compatible provider path with mock fallback.
- Optional Playwright MCP-compatible browser fetch provider behind the existing
  HTTP fallback path.
- Optional OpenSearch-compatible candidate history full-text projection.
- Optional generic webhook notification after push persistence.
- Provider choices and fallback behavior are surfaced through events, errors,
  tool results, or README boundaries.

Still not claimed:

- verified live OneSearch MCP deployment
- raw MCP protocol session management
- verified Microsoft Playwright MCP live-service deployment
- general autonomous browsing or production browser fleet
- production Elasticsearch/OpenSearch cluster hardening
- provider-specific Slack, enterprise WeChat, or email delivery
- production notification retry queue

### Phase 2D: Hybrid RAG And Dedup Enhancement

Status: implemented locally and deterministically; external vector/embedding
services are not claimed.

Evidence:

- `ccaea25 feat: add bm25 business context retrieval`
- `0432de2 feat: add local vector rerank retrieval`
- `c6acc8e feat: add local semantic dedup`
- `backend/app/rag/bm25_retriever.py`
- `backend/app/rag/local_vector_retriever.py`
- `backend/app/rag/hybrid_retriever.py`
- `backend/app/tools/semantic_dedup.py`
- `backend/tests/test_tools_and_eval.py`

Implemented scope:

- Business context retrieval combines keyword, BM25, deterministic local
  token-vector retrieval, and rerank metadata.
- Optional deterministic local semantic-like dedup runs after exact
  URL/title/content-fingerprint dedup.
- Drop reasons and retrieval metadata are visible in results.

Still not claimed:

- vector database retrieval
- external model embedding indexing
- production semantic clustering service

### Phase 2E: Richer Memory And Observability

Status: implemented for persisted business memory and quality trend summaries.

Evidence:

- `07939da feat: persist candidate memory records`
- `17bc411 feat: persist extracted item memory records`
- `7fe9381 feat: persist structured decision records`
- `98c24d2 feat: add richer eval fallback metrics`
- `ab60530 feat: add eval quality summary view`
- `bf8b637 docs: expose quality summary page`
- `8db0790 fix: accept history index events`
- `backend/app/storage/models.py`
- `backend/app/storage/repository.py`
- `backend/app/api/eval.py`
- `backend/app/templates/quality.html`
- `backend/tests/test_monitor_run_flow.py`
- `backend/tests/test_tools_and_eval.py`

Implemented scope:

- Candidate records are persisted beyond run snapshots.
- Extracted item records are persisted beyond run snapshots.
- Structured decision records are persisted beyond run snapshots.
- Eval metrics include fallback and trace-quality signals.
- `/api/eval/summary` exposes quality trend summaries.
- `/quality` exposes a minimal HTML quality summary page.
- Event schema accepts history-index events emitted by the optional index path.

### LLM-As-Judge Evaluation Contract

Status: implemented as a deterministic contract plus optional
OpenAI-compatible provider.

Evidence:

- `f456561 feat: add eval judge adapter`
- `0c6f934 feat: add openai compatible eval judge`
- `backend/app/eval/judge.py`
- `backend/app/core/config.py`
- `backend/tests/test_tools_and_eval.py`

Implemented scope:

- Deterministic `MockEvalJudge` keeps tests stable.
- Optional OpenAI-compatible judge provider is enabled only when configured.
- Provider failure falls back to deterministic judge behavior and remains
  visible through judge metadata.

Still not claimed:

- guaranteed live external judge availability
- provider-specific quality guarantees

### Local Docker Compose Stack

Status: implemented for local demonstration.

Evidence:

- `a658737 chore: add local docker compose stack`
- `docker-compose.yml`
- `backend/README.md`

Implemented scope:

- Local Compose stack starts backend, PostgreSQL, and Redis.
- Compose is documented as a local demonstration profile, not production
  deployment hardening.

### React + Vite Management Dashboard

Status: implemented as a local read-only dashboard over existing backend APIs.

Evidence:

- `9caa444 feat: add react dashboard`
- `docs/superpowers/specs/2026-06-17-react-dashboard-design.md`
- `docs/superpowers/plans/2026-06-17-react-dashboard.md`
- `frontend/src/App.tsx`
- `frontend/src/api/client.ts`
- `frontend/src/App.test.tsx`
- `frontend/src/api/client.test.ts`
- `frontend/Dockerfile`
- `docker-compose.yml`
- `backend/README.md`

Implemented scope:

- Standalone `frontend/` React + TypeScript + Vite app.
- Typed client consumption of existing backend APIs only:
  - `GET /api/topics`
  - `GET /api/pushes`
  - `GET /api/monitor/runs/{run_id}`
  - `GET /api/monitor/runs/{run_id}/events`
  - `GET /api/eval/summary`
- Read-only views for dashboard summary, topics, pushes, run detail, and trace
  timeline.
- Local demo Compose frontend service on port `5173`.
- README documentation for frontend commands and local-demo capability bounds.
- Existing FastAPI HTML pages remain available.

Still not claimed:

- production frontend deployment
- authentication or authorization
- write operations from the React dashboard
- realtime streaming via WebSocket or SSE
- replacement of existing FastAPI HTML pages

## Remaining Phase 2 Work

### Raw MCP Session Management

Status: not implemented and not currently claimed.

Current boundary:

- `OneSearchMCPGateway` is implemented as an optional OneSearch-compatible HTTP
  wrapper adapter behind explicit configuration.
- `LocalToolGateway` remains the deterministic default.
- MCP/provider unavailability is surfaced through tool metadata, run events,
  and eval fallback metrics.

Still not implemented:

- raw MCP protocol session management
- generalized MCP client lifecycle management
- verified live third-party MCP service availability claims

### Provider-Specific Notifications

Status: generic webhook implemented; Slack, enterprise WeChat, and email are not
implemented.

Target:

- Add one provider at a time only if endpoint shape, secrets, retry behavior, and
  failure visibility are frozen.

### Production Hardening

Status: not implemented.

Not claimed:

- deployment security hardening
- production browser fleet
- production OpenSearch management
- production notification delivery queues
- production observability stack such as Langfuse or OpenTelemetry

## Recommended Next Slice

The next high-value implementation slice is:

`Provider-specific notification -> explicit secrets/config -> failure visibility -> README truthfulness`

Reason:

- The generic webhook path is already implemented, so the next truthful gain is
  to add one concrete provider instead of broadening unverified claims.
- `DEVELOPMENT_GUIDE.md` explicitly lists Slack, enterprise WeChat, and email
  as target notification channels beyond webhook.
- This slice is narrower than raw MCP session management and can reuse the
  existing persisted push-record and notification event boundary.

Required constraints:

- Add one provider at a time.
- Keep webhook and disabled notification paths working unchanged.
- Surface provider-specific delivery failures through tool responses, run
  errors, and notification events.
- Do not claim retry queues, production delivery guarantees, or providers that
  are not implemented.
- Verify backend tests before committing.

## Verification Baseline

Before claiming any future slice complete, run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest -q
py -3.12 -m compileall app
cd E:\bgagent2\.worktrees\feat-industry-news-mvp
docker compose config --quiet
git diff --check
```

If a React/Vite frontend is added, also run its package-manager install/build
and any frontend test command documented in the frontend plan.
