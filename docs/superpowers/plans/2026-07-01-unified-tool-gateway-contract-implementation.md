# Unified Tool Gateway Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the unified tool-access contract into the gateway layer so the
run snapshot reports a real gateway-owned contract instead of a display-only
inference.

**Architecture:** Extend `ToolGateway` with a read-only access-contract method,
implement it in `LocalToolGateway` and `OneSearchMCPGateway`, then teach
`build_integration_runtime(...)` and finalize paths to prefer the gateway-owned
contract while preserving the existing truthful provider split.

**Tech Stack:** Python 3.12, FastAPI, LangGraph, pytest

---

### Task 1: Add Gateway-Level Contract Tests

**Files:**
- Modify: `backend/tests/test_tools_and_eval.py`
- Modify: `backend/app/mcp/gateway.py`
- Modify: `backend/app/mcp/local_gateway.py`
- Modify: `backend/app/mcp/onesearch_gateway.py`

- [ ] Add failing tests for `LocalToolGateway.describe_tool_access()`.
- [ ] Add failing tests for `OneSearchMCPGateway.describe_tool_access()`.
- [ ] Run `py -3.12 -m pytest backend/tests/test_tools_and_eval.py -q -k "tool_access_contract"` and verify failure.
- [ ] Implement the new abstract method and both gateway implementations.
- [ ] Re-run the same tests and verify pass.

### Task 2: Prefer Gateway-Owned Contract In Runtime Summary

**Files:**
- Modify: `backend/app/integrations/runtime_summary.py`
- Modify: `backend/app/agent/graph.py`
- Modify: `backend/app/agent/nodes.py`
- Modify: `backend/tests/test_tools_and_eval.py`
- Modify: `backend/tests/test_monitor_run_flow.py`

- [ ] Add failing tests proving `build_integration_runtime(..., gateway=...)`
      prefers gateway-provided tool-access data.
- [ ] Add failing run-snapshot coverage proving the existing truthful
      `mcp_gateway` vs `tool_gateway` split is preserved.
- [ ] Extend `build_integration_runtime(...)` with an optional gateway input.
- [ ] Pass the gateway into integration-runtime construction in graph/finalize
      paths.
- [ ] Re-run focused tests:
      `py -3.12 -m pytest backend/tests/test_tools_and_eval.py backend/tests/test_monitor_run_flow.py -q -k "tool_access_contract or integration_runtime"`

### Task 3: Keep Read Surfaces Stable

**Files:**
- Modify: `backend/app/templates/run_detail.html`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/api/types.ts`

- [ ] Verify current read surfaces still match the contract after the gateway
      source change.
- [ ] Only make code changes if the runtime-summary shape requires them.
- [ ] Re-run:
      `npm --prefix frontend test -- --run`
      `npm --prefix frontend run build`

### Task 4: Final Verification

**Files:**
- Modify: `PROJECT_TODO.md`

- [ ] Mark the unified tool gateway contract slice complete in project state if
      verification passes.
- [ ] Run:
      `py -3.12 -m pytest backend/tests/test_tools_and_eval.py backend/tests/test_monitor_run_flow.py -q`
      `npm --prefix frontend test -- --run`
      `git diff --check`
