# LangGraph Contract Tightening Design

**Goal:** Tighten the current LangGraph-based multi-agent runtime so the
resume-facing `LangGraph` claim rests on stable structured contracts rather
than primarily on legacy mirror fields and compatibility readback.

**Scope:** This design covers only the in-process LangGraph monitor runtime,
its state contracts, run readback shape, and runtime evidence surfaces. It does
not replace LangGraph, does not introduce distributed agents, and does not add
new providers.

**Why now:** The repository already has real planner, retrieval,
candidate-orchestration, extraction, and evaluation boundaries. RAG, MCP, and
Playwright now have materially stronger truthful runtime stories. The main
remaining gap is that too much API and UI readback still depends on mirrored
legacy fields instead of clearly exposing the structured LangGraph stage
outputs that now drive the run.

---

## 1. Current State

The current project already has a real top-level LangGraph flow:

- `supervisor_bootstrap`
- `planner_agent`
- `retrieval_agent`
- `candidate_task_orchestrator`
- `supervisor_finalize`

The runtime already preserves structured stage sections:

- `run_context`
- `business_memory`
- `planner_output`
- `retrieval_output`
- `extraction_output`
- `evaluation_output`

However, the truth boundary is still weaker than it should be for the resume:

- `GET /api/monitor/runs/{run_id}` still centers the compatibility snapshot
  fields such as `expanded_queries`, `candidate_items`, and `final_decisions`
- HTML run/detail pages are still oriented around those compatibility mirrors
- direct tests emphasize legacy field readback more than structured contract
  readback
- state ownership rules exist in code, but not all read surfaces make them
  obvious

This slice should tighten the contract without breaking the current project
demonstration flow.

## 2. Design Principles

The implementation must preserve these rules:

1. LangGraph remains the top-level orchestration backbone.
2. Structured stage sections are the primary truth; legacy mirrors are
   compatibility support only.
3. The public read surface may expose both structured and compatibility fields,
   but it must become obvious which one is authoritative.
4. No fake distributed-agent narrative may be introduced.
5. Candidate-level orchestration remains real and visible.
6. Changes must stay compatible with the existing admin/demo flow unless a
   safer additive contract can replace it cleanly.

## 3. Target Contract Boundary

The monitor run read surface should expose both:

1. Structured LangGraph stage outputs
2. Legacy compatibility mirrors

But the structured stage outputs should become first-class and explicit.

Target run-detail shape:

```json
{
  "run_id": "run_xxx",
  "topic_id": "topic_xxx",
  "trigger": "manual",
  "status": "completed",
  "run_context": {},
  "business_memory": {},
  "planner_output": {},
  "retrieval_output": {},
  "extraction_output": {},
  "evaluation_output": {},
  "integration_runtime": {},
  "candidate_task_summary": {},
  "expanded_queries": [],
  "candidate_items": [],
  "final_decisions": [],
  "errors": [],
  "started_at": "...",
  "finished_at": "..."
}
```

Contract rule:

- `planner_output`, `retrieval_output`, `extraction_output`, and
  `evaluation_output` are authoritative stage outputs
- `expanded_queries`, `candidate_items`, and `final_decisions` remain mirrored
  compatibility fields

## 4. State Ownership Rules

This slice should make stage ownership explicit.

### 4.1 Planner Ownership

`planner_output` owns:

- expanded query list
- query plan
- source plan
- retrieval strategy
- planning reasons

Legacy mirror:

- `expanded_queries`
- `source_plan`

### 4.2 Retrieval Ownership

`retrieval_output` owns:

- candidate pool
- source coverage
- retrieval failures
- provider fallbacks

Legacy mirror:

- `candidate_items`

### 4.3 Extraction Ownership

`extraction_output` owns:

- fetched contents
- evidence items
- extraction failures
- content fallbacks

Legacy mirrors:

- `fetched_contents`
- `extracted_items`

### 4.4 Evaluation Ownership

`evaluation_output` owns:

- deduped items
- scored items
- final decisions
- decision reasons
- push records
- eval result

Legacy mirrors:

- `deduped_items`
- `scored_items`
- `final_decisions`
- `decision_reasons`
- `push_records`
- `eval_result`

## 5. API Tightening

The monitor run detail API should evolve from “compatibility snapshot only” to
“structured readback plus compatibility mirrors.”

### 5.1 Additive Response Strategy

This slice should extend `MonitorRunStateResponse` with:

- `run_context`
- `business_memory`
- `planner_output`
- `retrieval_output`
- `extraction_output`
- `evaluation_output`

This is additive and should not break current users that only consume the
legacy fields.

### 5.2 Explicit Compatibility Note

README and demo-facing copy should explain:

- structured sections are the real stage contracts
- legacy fields remain exposed for compatibility and concise readback

## 6. UI Tightening

The minimal HTML surfaces do not need a full redesign, but they should make the
structured LangGraph story easier to demonstrate.

### 6.1 Run Detail Page

`GET /runs/{run_id}` should explain:

- this run is organized into planner, retrieval, candidate orchestration,
  extraction/evaluation, and finalize stages
- structured stage sections are queryable through the API
- compatibility mirrors still exist for concise readback

### 6.2 Resume Alignment Page

The resume-alignment page should be updated so the suggested interview wording
leans on:

- structured stage contracts
- candidate-level orchestration evidence
- API-visible readback of stage outputs

## 7. Verification Requirements

The implementation must prove three things.

### 7.1 Structured Readback Exists

Tests should show `GET /api/monitor/runs/{run_id}` returns:

- `planner_output`
- `retrieval_output`
- `extraction_output`
- `evaluation_output`

### 7.2 Structured And Legacy Fields Stay Consistent

Tests should show:

- `expanded_queries == planner_output.expanded_queries`
- `candidate_items == retrieval_output.candidate_pool`
- `final_decisions == evaluation_output.final_decisions`

where those outputs are present

### 7.3 Contract Evidence Is Visible

Tests or pages should show the run/detail surfaces mention:

- planner
- retrieval
- candidate orchestration
- structured stage evidence

## 8. Non-Goals

This slice does not require:

- removing all legacy mirror fields immediately
- redesigning the frontend dashboard
- changing persistence ownership
- replacing the current in-process orchestration model
- introducing new resume technologies

## 9. Acceptance Criteria

This slice is complete only when all of the following are true:

1. structured LangGraph stage outputs are exposed through the monitor run API
2. legacy compatibility mirrors still exist and remain consistent
3. state ownership across planner/retrieval/extraction/evaluation is explicit
   in code and read surfaces
4. HTML/readme wording makes the structured LangGraph contract visible
5. verification proves the structured contract is real and not just internal
   state

## 10. Truth Boundary After This Slice

After implementation, the project may truthfully say:

- the LangGraph runtime uses explicit structured stage contracts
- the public read surface exposes planner, retrieval, extraction, and
  evaluation outputs directly
- candidate-level orchestration remains part of the same LangGraph-backed run

It still must not say:

- agents are distributed across processes or machines
- the system uses an external workflow engine instead of LangGraph
