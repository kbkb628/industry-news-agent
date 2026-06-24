# LangGraph Contract Tightening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the real structured LangGraph stage contracts through the run
API and demo surfaces, while preserving existing compatibility mirrors.

**Architecture:** Keep the current in-process LangGraph monitor flow and its
existing structured state sections, but promote those sections into additive
public readback fields. Continue mirroring legacy compatibility fields from the
structured sections in `supervisor_finalize`, and tighten tests and copy so the
structured contracts become the primary truth boundary.

**Tech Stack:** Python 3.12, FastAPI, LangGraph, Pydantic, Jinja templates,
pytest

---

### Task 1: Extend The Monitor Run Response Contract

**Files:**
- Modify: `backend/app/schemas/monitor_schema.py`
- Modify: `backend/app/api/monitor.py`
- Test: `backend/tests/test_monitor_run_flow.py`

- [ ] **Step 1: Write the failing API contract tests**

Add assertions to `backend/tests/test_monitor_run_flow.py` so the completed run
detail API must include:

```python
assert "planner_output" in payload
assert "retrieval_output" in payload
assert "extraction_output" in payload
assert "evaluation_output" in payload
```

Also assert at least one structured consistency rule:

```python
assert payload["expanded_queries"] == payload["planner_output"]["expanded_queries"]
assert payload["candidate_items"] == payload["retrieval_output"]["candidate_pool"]
assert payload["final_decisions"] == payload["evaluation_output"]["final_decisions"]
```

- [ ] **Step 2: Run the focused API test to verify failure**

Run:

```powershell
py -3.12 -m pytest backend/tests/test_monitor_run_flow.py -q -k "run_detail_returns_completed_state"
```

Expected: FAIL because the API response model does not yet expose the
structured stage outputs.

- [ ] **Step 3: Add structured fields to the response model and route**

Update `backend/app/schemas/monitor_schema.py`:

```python
    run_context: dict[str, Any] = Field(default_factory=dict)
    business_memory: dict[str, Any] = Field(default_factory=dict)
    planner_output: dict[str, Any] = Field(default_factory=dict)
    retrieval_output: dict[str, Any] = Field(default_factory=dict)
    extraction_output: dict[str, Any] = Field(default_factory=dict)
    evaluation_output: dict[str, Any] = Field(default_factory=dict)
```

Update `backend/app/api/monitor.py` `get_run_state()` to return:

```python
        run_context=dict(snapshot.get("run_context", {})),
        business_memory=dict(snapshot.get("business_memory", {})),
        planner_output=dict(snapshot.get("planner_output", {})),
        retrieval_output=dict(snapshot.get("retrieval_output", {})),
        extraction_output=dict(snapshot.get("extraction_output", {})),
        evaluation_output=dict(snapshot.get("evaluation_output", {})),
```

- [ ] **Step 4: Re-run the focused API test**

Run:

```powershell
py -3.12 -m pytest backend/tests/test_monitor_run_flow.py -q -k "run_detail_returns_completed_state"
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/monitor_schema.py backend/app/api/monitor.py backend/tests/test_monitor_run_flow.py
git commit -m "feat: expose structured langgraph stage outputs"
```

### Task 2: Tighten Structured-And-Legacy Consistency Tests

**Files:**
- Modify: `backend/tests/test_monitor_run_flow.py`
- Modify: `backend/app/agent/nodes.py`

- [ ] **Step 1: Write the failing consistency tests**

Add a focused test asserting `supervisor_finalize_node(...)` preserves equality
between structured and legacy fields:

```python
assert result["expanded_queries"] == result["planner_output"]["expanded_queries"]
assert result["candidate_items"] == result["retrieval_output"]["candidate_pool"]
assert result["fetched_contents"] == result["extraction_output"]["fetched_contents"]
assert result["extracted_items"] == result["extraction_output"]["evidence_items"]
assert result["final_decisions"] == result["evaluation_output"]["final_decisions"]
```

- [ ] **Step 2: Run the finalize-focused test to verify failure if any mirror is missing**

Run:

```powershell
py -3.12 -m pytest backend/tests/test_monitor_run_flow.py -q -k "supervisor_finalize_mirrors_structured_outputs_to_legacy_fields"
```

Expected: PASS or targeted FAIL revealing any remaining inconsistency. If it
already passes, extend the assertion set to include the structured fields now
exposed by the API and then proceed with the mirror cleanup only if needed.

- [ ] **Step 3: Tighten finalize logic only if needed**

If the new assertions reveal gaps, update `backend/app/agent/nodes.py`
`supervisor_finalize_node(...)` so every compatibility mirror is populated from
its authoritative structured stage section before persistence.

- [ ] **Step 4: Re-run the finalize-focused test**

Run:

```powershell
py -3.12 -m pytest backend/tests/test_monitor_run_flow.py -q -k "supervisor_finalize_mirrors_structured_outputs_to_legacy_fields"
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/nodes.py backend/tests/test_monitor_run_flow.py
git commit -m "test: tighten structured and legacy state consistency"
```

### Task 3: Tighten Demo Copy Around Structured LangGraph Contracts

**Files:**
- Modify: `backend/app/templates/run_detail.html`
- Modify: `backend/app/templates/resume_alignment.html`
- Modify: `backend/README.md`
- Test: `backend/tests/test_monitor_run_flow.py`

- [ ] **Step 1: Write the failing wording test**

Extend the existing static page test to assert the pages reference structured
stage evidence, for example:

```python
assert "structured stage evidence" in run_detail_response.text
assert "structured stage contracts" in resume_alignment_response.text
```

- [ ] **Step 2: Run the wording test to verify failure**

Run:

```powershell
py -3.12 -m pytest backend/tests/test_monitor_run_flow.py -q -k "static_run_pages_describe_runtime_evidence_sections"
```

Expected: FAIL because the wording does not yet mention structured stage
contracts directly.

- [ ] **Step 3: Update explanatory copy**

Update `backend/app/templates/run_detail.html` so it explicitly says:

- the run is organized into planner, retrieval, candidate orchestration, and
  evaluation sections
- structured stage evidence is exposed through the run API
- compatibility mirrors remain for concise readback

Update `backend/app/templates/resume_alignment.html` so it explicitly says:

- LangGraph uses structured stage contracts
- candidate-level orchestration runs under that backbone
- APIs expose those stage outputs directly

Update `backend/README.md` in the architecture section so it explains:

- structured sections are the authoritative runtime contracts
- legacy fields remain compatibility mirrors

- [ ] **Step 4: Re-run the wording test**

Run:

```powershell
py -3.12 -m pytest backend/tests/test_monitor_run_flow.py -q -k "static_run_pages_describe_runtime_evidence_sections"
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/templates/run_detail.html backend/app/templates/resume_alignment.html backend/README.md backend/tests/test_monitor_run_flow.py
git commit -m "docs: tighten langgraph contract demo wording"
```

### Task 4: Full Verification And Milestone Closure

**Files:**
- Modify: `PROJECT_TODO.md`

- [ ] **Step 1: Run focused LangGraph regressions**

Run:

```powershell
py -3.12 -m pytest backend/tests/test_monitor_run_flow.py -q -k "run_detail_returns_completed_state or supervisor_finalize or static_run_pages"
```

Expected: PASS

- [ ] **Step 2: Run full backend suite**

Run:

```powershell
py -3.12 -m pytest backend -q
```

Expected: PASS

- [ ] **Step 3: Run hygiene checks**

Run:

```powershell
git diff --check
git status --short --untracked-files=all
```

Expected: no whitespace errors and only intended LangGraph-tightening changes
before commit

- [ ] **Step 4: Update milestone tracking**

Update `PROJECT_TODO.md` to add:

- `implement langgraph contract tightening slice`
- `spec and planning for langgraph contract tightening`

- [ ] **Step 5: Commit**

```bash
git add PROJECT_TODO.md backend
git commit -m "feat: complete langgraph contract tightening slice"
```

## Self-Review

### Spec coverage

- API-visible structured stage outputs: covered by Task 1
- structured-versus-legacy consistency: covered by Task 2
- demo/readme evidence surfaces: covered by Task 3
- verification and closure: covered by Task 4

### Placeholder scan

- No `TBD`, `TODO`, or deferred placeholders remain
- Each task includes exact files and exact commands

### Type consistency

- One stable structured contract vocabulary is used throughout:
  `run_context`, `business_memory`, `planner_output`, `retrieval_output`,
  `extraction_output`, `evaluation_output`
