# Real Multi-Agent Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the current monitor workflow into a real in-process multi-agent architecture with supervisor-owned orchestration and structured stage contracts, while preserving the existing external API surface.

**Architecture:** Replace the fine-grained linear LangGraph chain with stage-level agent nodes: supervisor bootstrap, planner agent, retrieval agent, extraction agent, evaluation agent, and supervisor finalization. Introduce structured shared-state sections and compatibility mirror fields so specialist agents can collaborate through explicit contracts without breaking existing run APIs and pages.

**Tech Stack:** Python, FastAPI, LangGraph, Pydantic, pytest

---

### Task 1: Freeze Multi-Agent State Contracts

**Files:**
- Create: `backend/app/agent/contracts.py`
- Modify: `backend/app/agent/state.py`
- Test: `backend/tests/test_supporting_schema_contracts.py`

- [ ] **Step 1: Write the failing contract-shape test**

Add a test that imports the new contract helpers and verifies the monitor state exposes the new top-level sections required by the design:

```python
def test_multi_agent_state_contract_sections_exist() -> None:
    from app.agent.contracts import (
        build_empty_business_memory,
        build_empty_evaluation_output,
        build_empty_extraction_output,
        build_empty_planner_output,
        build_empty_retrieval_output,
        build_empty_run_context,
    )

    run_context = build_empty_run_context(run_id="run_001", topic_id="topic_001")
    assert run_context["run_id"] == "run_001"
    assert run_context["topic_id"] == "topic_001"
    assert run_context["status"] == "created"

    assert build_empty_business_memory()["push_history"] == []
    assert build_empty_planner_output()["source_plan"] == []
    assert build_empty_retrieval_output()["candidate_pool"] == []
    assert build_empty_extraction_output()["evidence_items"] == []
    assert build_empty_evaluation_output()["final_decisions"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_supporting_schema_contracts.py::test_multi_agent_state_contract_sections_exist -q
```

Expected: FAIL because `app.agent.contracts` does not exist yet.

- [ ] **Step 3: Write minimal contract helpers and update state typing**

Create `backend/app/agent/contracts.py` with focused builders for the new shared-state sections and update `backend/app/agent/state.py` so `MonitorState` includes:

- `run_context`
- `business_memory`
- `planner_output`
- `retrieval_output`
- `extraction_output`
- `evaluation_output`

Keep legacy fields on `MonitorState` for compatibility.

- [ ] **Step 4: Run targeted test to verify it passes**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_supporting_schema_contracts.py::test_multi_agent_state_contract_sections_exist -q
```

Expected: PASS.

- [ ] **Step 5: Commit contract milestone**

```bash
git add backend/app/agent/contracts.py backend/app/agent/state.py backend/tests/test_supporting_schema_contracts.py
git commit -m "feat: add multi-agent state contracts"
```

### Task 2: Build PlannerAgent

**Files:**
- Create: `backend/app/agent/planner_agent.py`
- Modify: `backend/app/agent/planner.py`
- Modify: `backend/app/agent/nodes.py`
- Test: `backend/tests/test_tools_and_eval.py`

- [ ] **Step 1: Write the failing planner-agent behavior test**

Add a test that verifies planner output is context-aware instead of static:

```python
def test_planner_agent_builds_context_aware_plan() -> None:
    from app.agent.planner_agent import PlannerAgent
    from app.llm.mock_client import MockLLM

    agent = PlannerAgent(llm=MockLLM())
    state = {
        "topic": {
            "name": "AI Agent Funding",
            "trusted_sources": ["techcrunch.com", "github.com"],
        },
        "business_memory": {
            "seed_keywords": ["AI Agent", "funding"],
            "business_context": {
                "documents": [
                    {"title": "Trusted sources improve push quality"},
                    {"title": "Funding events matter for this topic"},
                ]
            },
            "push_history": [{"title": "Previous funding alert"}],
            "trusted_sources": ["techcrunch.com", "github.com"],
        },
        "planner_output": {},
    }

    result = agent.run(state)
    planner_output = result["planner_output"]

    assert planner_output["expanded_queries"]
    assert planner_output["query_plan"]
    assert planner_output["source_plan"]
    assert planner_output["retrieval_strategy"]["mode"] == "rss_first"
    assert planner_output["planning_reasons"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_tools_and_eval.py::test_planner_agent_builds_context_aware_plan -q
```

Expected: FAIL because `PlannerAgent` does not exist.

- [ ] **Step 3: Implement PlannerAgent and stop using static source planning**

Create `backend/app/agent/planner_agent.py` with a `PlannerAgent.run(state)` method that:

- reads topic and business memory
- expands keywords with the existing LLM client
- builds a structured `query_plan`
- builds a structured `source_plan`
- sets `retrieval_strategy` and `planning_reasons`

Reduce `backend/app/agent/planner.py` to focused helper logic used by the agent instead of returning a static tuple.

- [ ] **Step 4: Run targeted planner tests**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_tools_and_eval.py::test_planner_agent_builds_context_aware_plan -q
```

Expected: PASS.

- [ ] **Step 5: Commit planner milestone**

```bash
git add backend/app/agent/planner_agent.py backend/app/agent/planner.py backend/tests/test_tools_and_eval.py
git commit -m "feat: add planner agent orchestration"
```

### Task 3: Build RetrievalAgent And ExtractionAgent

**Files:**
- Create: `backend/app/agent/retrieval_agent.py`
- Create: `backend/app/agent/extraction_agent.py`
- Modify: `backend/app/agent/nodes.py`
- Test: `backend/tests/test_monitor_run_flow.py`

- [ ] **Step 1: Write failing agent-stage tests**

Add targeted tests that assert:

- RetrievalAgent writes `retrieval_output.candidate_pool`
- RetrievalAgent captures provider fallback metadata
- ExtractionAgent writes `extraction_output.evidence_items`

Example skeleton:

```python
def test_retrieval_agent_writes_candidate_pool() -> None:
    from app.agent.retrieval_agent import RetrievalAgent
    from app.mcp.local_gateway import LocalToolGateway

    gateway = LocalToolGateway()
    state = {
        "run_context": {"run_id": "run_001"},
        "topic": {"topic_id": "topic_001", "name": "AI Agent"},
        "planner_output": {
            "source_plan": [{"tool_name": "mock_search", "priority": 1}],
            "retrieval_strategy": {"mode": "rss_first"},
        },
        "retrieval_output": {},
        "tool_results": [],
        "errors": [],
        "events": [],
    }

    agent = RetrievalAgent(gateway=gateway)
    result = agent.run(state)
    assert "candidate_pool" in result["retrieval_output"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run the targeted retrieval and extraction tests you added:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_monitor_run_flow.py -k "retrieval_agent or extraction_agent" -q
```

Expected: FAIL because the agent modules do not exist.

- [ ] **Step 3: Implement RetrievalAgent and ExtractionAgent**

Create:

- `backend/app/agent/retrieval_agent.py`
- `backend/app/agent/extraction_agent.py`

Move candidate retrieval logic into RetrievalAgent and content-fetch plus extraction logic into ExtractionAgent. They must write:

- `retrieval_output.candidate_pool`
- `retrieval_output.source_coverage`
- `retrieval_output.provider_fallbacks`
- `extraction_output.fetched_contents`
- `extraction_output.evidence_items`
- `extraction_output.content_fallbacks`

- [ ] **Step 4: Run targeted stage tests**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_monitor_run_flow.py -k "retrieval_agent or extraction_agent" -q
```

Expected: PASS.

- [ ] **Step 5: Commit retrieval/extraction milestone**

```bash
git add backend/app/agent/retrieval_agent.py backend/app/agent/extraction_agent.py backend/app/agent/nodes.py backend/tests/test_monitor_run_flow.py
git commit -m "feat: add retrieval and extraction agents"
```

### Task 4: Build EvaluationAgent And Supervisor Finalization

**Files:**
- Create: `backend/app/agent/evaluation_agent.py`
- Modify: `backend/app/agent/nodes.py`
- Modify: `backend/app/agent/graph.py`
- Modify: `backend/app/api/monitor.py`
- Test: `backend/tests/test_monitor_run_flow.py`

- [ ] **Step 1: Write failing compatibility and lifecycle tests**

Add tests that assert:

- EvaluationAgent writes `evaluation_output`
- supervisor finalization mirrors compatibility fields back to legacy top-level fields
- full monitor run still returns legacy fields expected by current APIs

Example assertion targets:

```python
assert result["evaluation_output"]["final_decisions"]
assert result["final_decisions"] == result["evaluation_output"]["final_decisions"]
assert result["eval_result"] == result["evaluation_output"]["eval_result"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_monitor_run_flow.py -k "evaluation_agent or compatibility" -q
```

Expected: FAIL because evaluation output and supervisor mirroring are not implemented.

- [ ] **Step 3: Implement EvaluationAgent and stage-level graph orchestration**

Create `backend/app/agent/evaluation_agent.py` and refactor `backend/app/agent/graph.py` so the graph becomes:

- `supervisor_bootstrap`
- `planner_agent`
- `retrieval_agent`
- `extraction_agent`
- `evaluation_agent`
- `supervisor_finalize`

Move:

- dedup
- score
- decide push
- rule/eval scoring

into EvaluationAgent. Move final persistence and compatibility mirroring into supervisor finalization code.

- [ ] **Step 4: Run focused integration tests**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_monitor_run_flow.py -k "evaluation_agent or compatibility or monitor_graph" -q
```

Expected: PASS.

- [ ] **Step 5: Commit orchestration milestone**

```bash
git add backend/app/agent/evaluation_agent.py backend/app/agent/nodes.py backend/app/agent/graph.py backend/app/api/monitor.py backend/tests/test_monitor_run_flow.py
git commit -m "feat: orchestrate real multi-agent monitor flow"
```

### Task 5: Full Verification And Cleanup

**Files:**
- Modify: any touched files needed for final cleanup

- [ ] **Step 1: Run full backend test suite**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 2: Run compile verification**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m compileall app
```

Expected: exit 0.

- [ ] **Step 3: Run git diff hygiene check**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp
git diff --check
git status --short
```

Expected: no diff-check errors and only intended multi-agent changes remain.

- [ ] **Step 4: Commit final verified implementation**

```bash
git add backend docs/superpowers/plans/2026-06-17-real-multi-agent-architecture.md
git commit -m "feat: implement real multi-agent architecture"
```
