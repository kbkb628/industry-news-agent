# Resume Gap Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining code-vs-resume gaps without overstating optional integrations or proxy metrics.

**Architecture:** Keep the existing FastAPI + LangGraph single-process monitor topology, but strengthen the remaining weak spots in the runtime truth surface. Work in dependency order: first make the tool-access contract more unified and explicit, then either land or scope down the external-provider and metric wording gaps, and finally reconcile the demo/read surfaces.

**Tech Stack:** Python 3.12, FastAPI, LangGraph, SQLAlchemy, PostgreSQL, Redis, Redis Stream, pytest, React, Vite

---

### Task 1: Make Tool Access Wording More Truthful And More Unified

**Files:**
- Modify: `backend/tests/test_tools_and_eval.py`
- Modify: `backend/tests/test_monitor_run_flow.py`
- Modify: `backend/app/mcp/gateway.py`
- Modify: `backend/app/mcp/local_gateway.py`
- Modify: `backend/app/mcp/onesearch_gateway.py`
- Modify: `backend/app/integrations/runtime_summary.py`
- Modify: `backend/app/templates/run_detail.html`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/api/types.ts`
- Modify: `docs/resume-alignment.md`

- [ ] Add failing tests proving runtime evidence must distinguish `unified tool gateway contract` from `provider actually runs through MCP`.
- [ ] Extend the gateway/runtime contract so `search`, `browser`, and `notification` all report through one unified tool-access surface, while still truthfully showing which provider path is local vs MCP-backed.
- [ ] Update read surfaces so reviewers can see `tool_access_contract` separately from `provider_path`.
- [ ] Re-run focused verification:
  `py -3.12 -m pytest backend/tests/test_tools_and_eval.py backend/tests/test_monitor_run_flow.py -q -k "integration_runtime or notification_send or onesearch"`
  `npm --prefix frontend test -- --run`

### Task 2: Resolve The Resume-Level Playwright / OpenSearch / MCP Boundary Gap

**Files:**
- Modify: `backend/tests/test_tools_and_eval.py`
- Modify: `backend/README.md`
- Modify: `README.md`
- Modify: `docs/resume-alignment.md`
- Modify: `backend/app/templates/resume_alignment.html`

- [ ] Decide and encode one truthful presentation rule: these adapters stay optional boundaries unless a concrete runtime proof exists.
- [ ] Add or tighten tests/docs so the repo never implies Playwright MCP, OpenSearch, or general MCP availability when only adapter code exists.
- [ ] Re-run focused verification:
  `py -3.12 -m pytest backend/tests/test_tools_and_eval.py -q -k "playwright or opensearch or onesearch"`

### Task 3: Tighten Metric Naming Around Recall / False Positive / Cost

**Files:**
- Modify: `backend/tests/test_tools_and_eval.py`
- Modify: `backend/app/eval/rule_scorer.py`
- Modify: `backend/app/templates/quality.html`
- Modify: `frontend/src/App.tsx`
- Modify: `README.md`
- Modify: `docs/resume-alignment.md`

- [ ] Add failing tests proving metric labels shown to users remain explicitly proxy-oriented where the implementation is heuristic.
- [ ] Keep existing stored fields, but make user-facing copy and docs consistently say `proxy` for recall, false positive, latency, and runtime cost.
- [ ] Re-run focused verification:
  `py -3.12 -m pytest backend/tests/test_tools_and_eval.py -q -k "quality_evidence_metrics or quality_trend_metrics"`
  `npm --prefix frontend test -- --run`

### Task 4: Resolve The Concurrency / Worker / Circuit-Breaker Wording Gap

**Files:**
- Modify: `backend/README.md`
- Modify: `README.md`
- Modify: `docs/resume-alignment.md`
- Modify: `backend/app/templates/resume_alignment.html`

- [ ] Reconcile wording so the code is described as `bounded concurrency + retry + timeout + rate/usage controls` unless a real circuit-breaker implementation is added.
- [ ] Keep Redis Stream worker governance claims, but avoid language that sounds like a distributed stage-worker fleet unless that architecture exists in code.
- [ ] Re-run repo checks:
  `git diff --check`

### Task 5: Final Verification And Commit

**Files:**
- Modify: `PROJECT_TODO.md`

- [ ] Update project TODO with the completed resume-gap closure milestone.
- [ ] Run broad verification:
  `py -3.12 -m pytest backend/tests/test_demo_bootstrap.py backend/tests/test_tools_and_eval.py backend/tests/test_monitor_run_flow.py backend/tests/test_topics_api.py -q`
  `npm --prefix frontend test -- --run`
  `npm --prefix frontend run build`
  `git diff --check`
  `git status --short`
- [ ] Commit:
  `git commit -m "feat: close remaining resume wording gaps"`

## Self-Review

### Spec Coverage

- unified MCP/tool-access contract truth: Task 1
- Playwright / OpenSearch / MCP boundary truth: Task 2
- proxy metric wording truth: Task 3
- concurrency / worker / circuit-breaker wording truth: Task 4
- final verification / cleanup: Task 5

### Placeholder Scan

- No `TODO` or `TBD` placeholders are used as executable instructions.
- Each task lists files and concrete verification commands.

### Type Consistency

- `integration_runtime` remains the shared read surface for runtime evidence.
- `tool_access` stays the summary surface for access path reporting.
- `candidate_*_concurrency` continues to describe bounded in-process candidate-stage parallelism.
