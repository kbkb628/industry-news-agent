# Resume Truth Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the codebase truthfully satisfy the explicit technical choices and capability wording already written in the resume for the industry-news structured push agent.

**Architecture:** Keep the existing FastAPI + LangGraph single-process topology, but strengthen the missing runtime responsibilities that the resume currently overstates. Implement the remaining work in dependency order: first unify the tool/gateway contract, then make candidate-stage execution truly concurrent in-process, then harden Redis short-lived state, then upgrade RAG retrieval, then make the browser path more real, and finally extend quality evidence surfaces.

**Tech Stack:** Python 3.12, FastAPI, LangGraph, SQLAlchemy, PostgreSQL, Redis, Redis Stream, APScheduler, pytest, Playwright-compatible HTTP tooling, OpenSearch-compatible HTTP tooling

---

### Task 1: Tighten MCP / ToolGateway Into A Real Unified Tool Access Layer

**Files:**
- Modify: `backend/tests/test_tools_and_eval.py`
- Modify: `backend/tests/test_monitor_run_flow.py`
- Modify: `backend/app/integrations/runtime_summary.py`
- Modify: `backend/app/mcp/gateway.py`
- Modify: `backend/app/mcp/local_gateway.py`
- Modify: `backend/app/mcp/onesearch_gateway.py`
- Modify: `backend/app/tools/registry.py`
- Modify: `backend/README.md`

- [ ] Add failing tests proving runtime evidence must cover `search_news`, browser-backed fetch, and notification delivery under one gateway/runtime contract.
- [ ] Implement the minimal gateway contract tightening so runtime evidence no longer treats notification as an untracked side path.
- [ ] Keep existing local fallback behavior, but make the selected path and fallback path explicit for search, browser, and notification.
- [ ] Re-run focused tests:
  `py -3.12 -m pytest backend/tests/test_tools_and_eval.py backend/tests/test_monitor_run_flow.py -q -k "integration_runtime or notification_send or onesearch"`
- [ ] Commit:
  `git commit -m "feat: tighten unified tool gateway runtime evidence"`

### Task 2: Make Candidate-Stage Execution Truly Limited-Concurrent In Process

**Files:**
- Modify: `backend/tests/test_monitor_run_flow.py`
- Modify: `backend/tests/test_tools_and_eval.py`
- Modify: `backend/app/agent/candidate_orchestrator.py`
- Modify: `backend/app/agent/nodes.py`
- Modify: `backend/app/agent/extraction_agent.py`
- Modify: `backend/app/agent/evaluation_agent.py`
- Modify: `backend/README.md`

- [ ] Add failing tests that prove same-stage candidate tasks can execute concurrently inside one process while preserving ordering, retry, and persisted task-ledger evidence.
- [ ] Replace the current sequential queue-walk with bounded in-process stage workers using the existing `candidate_*_concurrency` settings.
- [ ] Preserve current durable candidate-task ledger records and event semantics.
- [ ] Re-run focused tests:
  `py -3.12 -m pytest backend/tests/test_monitor_run_flow.py backend/tests/test_tools_and_eval.py -q -k "candidate_task or concurrency"`
- [ ] Commit:
  `git commit -m "feat: add real in-process candidate concurrency"`

### Task 3: Make Redis Own Short-Lived Dedup And Coordination State

**Files:**
- Modify: `backend/tests/test_monitor_run_flow.py`
- Modify: `backend/tests/test_tools_and_eval.py`
- Modify: `backend/app/storage/redis_store.py`
- Modify: `backend/app/scheduler/worker.py`
- Modify: `backend/app/api/monitor.py`
- Modify: `backend/README.md`

- [ ] Add failing tests for Redis-owned active-run coordination, short-lived dedup keys, and retry-state visibility.
- [ ] Implement Redis-backed short-lived coordination helpers without moving durable business facts out of PostgreSQL.
- [ ] Keep explicit in-memory fallback when Redis is unavailable.
- [ ] Re-run focused tests:
  `py -3.12 -m pytest backend/tests/test_tools_and_eval.py backend/tests/test_monitor_run_flow.py -q -k "redis or retry or active_run"`
- [ ] Commit:
  `git commit -m "feat: harden redis short-lived coordination state"`

### Task 4: Upgrade RAG From Embedding-Like To Real Embedding Retrieval

**Files:**
- Modify: `backend/tests/test_tools_and_eval.py`
- Modify: `backend/tests/test_monitor_run_flow.py`
- Modify: `backend/app/rag/local_vector_retriever.py`
- Modify: `backend/app/rag/hybrid_retriever.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/README.md`

- [ ] Add failing tests that prove the vector path is no longer only token-overlap cosine dressed as embedding-like retrieval.
- [ ] Introduce a real local embedding generation path and keep BM25 + rerank on top of it.
- [ ] Preserve the existing retrieval contract shape returned into `business_context`.
- [ ] Re-run focused tests:
  `py -3.12 -m pytest backend/tests/test_tools_and_eval.py backend/tests/test_monitor_run_flow.py -q -k "hybrid_context or embedding or bm25"`
- [ ] Commit:
  `git commit -m "feat: upgrade rag embedding retrieval path"`

### Task 5: Make Playwright Path Realer And More Verifiable

**Files:**
- Modify: `backend/tests/test_tools_and_eval.py`
- Modify: `backend/tests/test_monitor_run_flow.py`
- Modify: `backend/app/tools/browser_fetch_tool.py`
- Modify: `backend/app/integrations/runtime_summary.py`
- Modify: `backend/README.md`

- [ ] Add failing tests that prove browser-backed fetch attempts, allowed-domain governance, fallback reasons, and run-level evidence are visible end-to-end.
- [ ] Strengthen the Playwright-compatible browser path so the runtime evidence reflects actual browser use and not just configuration state.
- [ ] Re-run focused tests:
  `py -3.12 -m pytest backend/tests/test_tools_and_eval.py backend/tests/test_monitor_run_flow.py -q -k "browser_fallback or playwright"`
- [ ] Commit:
  `git commit -m "feat: strengthen playwright runtime evidence"`

### Task 6: Extend Quality Metrics And Admin Read Surfaces To Match Resume Wording

**Files:**
- Modify: `backend/tests/test_tools_and_eval.py`
- Modify: `backend/tests/test_monitor_run_flow.py`
- Modify: `backend/app/eval/rule_scorer.py`
- Modify: `backend/app/api/eval.py`
- Modify: `backend/app/templates/quality.html`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/App.test.tsx`
- Modify: `README.md`
- Modify: `docs/resume-alignment.md`

- [ ] Add failing tests for recall, dedup rate, duplicate/false-positive proxy metrics, tool success rate, latency, and runtime-cost proxy evidence.
- [ ] Extend the eval summary contract and read surfaces without overstating unavailable production observability.
- [ ] Re-run focused backend and frontend verification:
  `py -3.12 -m pytest backend/tests/test_tools_and_eval.py backend/tests/test_monitor_run_flow.py -q`
  `npm --prefix frontend test -- --run`
  `npm --prefix frontend run build`
- [ ] Commit:
  `git commit -m "feat: extend quality evidence surfaces"`

### Task 7: Final Resume-Truth Verification

**Files:**
- Modify: `README.md`
- Modify: `backend/README.md`
- Modify: `PROJECT_TODO.md`
- Modify: `docs/resume-alignment.md`

- [ ] Reconcile docs with the final runtime truth after Tasks 1-6.
- [ ] Run broad verification:
  `py -3.12 -m pytest backend/tests/test_demo_bootstrap.py backend/tests/test_tools_and_eval.py backend/tests/test_monitor_run_flow.py backend/tests/test_topics_api.py -q`
  `npm --prefix frontend test -- --run`
  `npm --prefix frontend run build`
  `git diff --check`
  `git status --short`
- [ ] Commit:
  `git commit -m "feat: complete resume truth alignment"`

## Self-Review

### Spec Coverage

- `MCP / Tool Use`: Task 1
- `high-concurrency task governance`: Tasks 2 and 3
- `Redis / Redis Stream`: Task 3
- `RAG embedding + BM25 + rerank`: Task 4
- `Playwright`: Task 5
- `quality metrics and visual evidence`: Task 6
- final truth / docs closure: Task 7

### Placeholder Scan

- No unresolved `TODO` or `TBD` markers are used as plan steps.
- Each task names its code/test/doc files and verification commands.

### Type Consistency

- `ToolGateway` remains the shared abstraction for tool access.
- `candidate_*_concurrency` remains the settings surface for candidate-stage limits.
- `integration_runtime` remains the visible run-level evidence section.
