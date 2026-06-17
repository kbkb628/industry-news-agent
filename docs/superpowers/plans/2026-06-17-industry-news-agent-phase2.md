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
- `backend/app/tools/registry.py`
- `backend/app/tools/browser_fetch_tool.py`
- `backend/app/search/history_index.py`
- `backend/app/tools/notification_tool.py`
- `backend/README.md`

Implemented scope:

- Optional OpenWebSearch-compatible provider path with mock fallback.
- Optional Playwright MCP-compatible browser fetch provider behind the existing
  HTTP fallback path.
- Optional OpenSearch-compatible candidate history full-text projection.
- Optional generic webhook notification after push persistence.
- Provider choices and fallback behavior are surfaced through events, errors,
  tool results, or README boundaries.

Still not claimed:

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

## Remaining Phase 2 Work

### React + Vite Management Dashboard

Status: not implemented.

Target:

- React admin dashboard showing topics, candidate/push data, run detail, trace
  timeline, and quality scores.
- Consume existing backend APIs instead of changing backend contracts first.
- Keep existing minimal HTML pages until the React dashboard is verified.
- Add frontend service to Docker Compose only as a local demo path.

Next required step:

- Freeze frontend page scope and API contract in a design spec before coding.

### Real OneSearch MCP Gateway Boundary

Status: not implemented as a true MCP client.

Target:

- Keep `LocalToolGateway` as deterministic default.
- Add a real MCP gateway/client boundary only behind explicit configuration.
- Surface MCP unavailability as events/errors and fall back according to
  `DEVELOPMENT_GUIDE.md`.
- Do not let Agent nodes depend directly on a concrete MCP server.

Next required step:

- Decide whether this should be a real MCP protocol client, an HTTP wrapper
  adapter, or a documented integration boundary. The choice must be explicit
  before implementation.

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

`React + Vite dashboard -> consume existing APIs -> local Compose frontend -> README route documentation`

Reason:

- It directly addresses `DEVELOPMENT_GUIDE.md` Phase 2's React management
  dashboard requirement.
- It improves project demonstration value without changing backend data
  contracts.
- Existing APIs already expose the required data for a first dashboard.

Required constraints:

- Do not remove existing FastAPI HTML pages until the React app is verified.
- Do not claim production frontend deployment.
- Do not add new backend APIs unless an existing endpoint is insufficient and
  the contract is documented first.
- Verify frontend build and backend tests before committing.

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
