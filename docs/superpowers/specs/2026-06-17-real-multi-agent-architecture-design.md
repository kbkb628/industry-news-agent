# Real Multi-Agent Architecture Design

## 1. Purpose

This document upgrades the current monitor workflow from a truthful but mostly
linear LangGraph pipeline into a real in-process multi-agent architecture that
better matches the project narrative in the resume and `DEVELOPMENT_GUIDE.md`.

The target is not distributed execution. The target is a real single-system
multi-agent collaboration model with:

- explicit agent roles
- explicit agent input/output contracts
- supervisor-owned orchestration
- stable shared state semantics
- compatibility with current APIs during migration

## 2. Why The Current Structure Is Not Enough

The current monitor graph is a fixed linear node chain:

`load -> retrieve_business_context -> expand_queries -> plan_sources -> retrieve_candidates -> fetch_contents -> extract_structured_items -> deduplicate_items -> score_items -> decide_push -> persist_push_records -> evaluate_run`

This works functionally, but it undersells three resume claims:

1. real Planner / Retrieval / Extraction / Evaluation agent separation
2. shared-state-based multi-agent collaboration
3. task planning as an independent capability rather than a thin helper

The current `planner.py` is especially weak because it returns a static source
plan independent of topic, context, history, or degradation signals.

## 3. Architectural Direction

Adopt a `Supervisor + specialist agents` architecture inside the existing
FastAPI/LangGraph system.

The multi-agent structure is:

```text
SupervisorAgent
  -> PlannerAgent
  -> RetrievalAgent
  -> ExtractionAgent
  -> EvaluationAgent
  -> Supervisor finalization
```

The supervisor remains responsible for lifecycle control and final persistence.
Each specialist agent owns a meaningful business stage and exchanges structured
contracts rather than anonymous flat state fragments.

## 4. Agent Responsibilities

### 4.1 SupervisorAgent

Responsibilities:

- initialize run context
- load topic and history memory
- dispatch specialist agents in order
- enforce stage transition rules
- accumulate global errors and events
- finalize run persistence and status

The supervisor is the only unit that owns the run lifecycle.

### 4.2 PlannerAgent

Responsibilities:

- consume topic definition and business memory
- consume RAG business context
- expand queries
- produce retrieval planning outputs
- decide source ordering and fallback posture

PlannerAgent must no longer return a static source list.

### 4.3 RetrievalAgent

Responsibilities:

- execute candidate retrieval based on planner outputs
- maintain candidate pool and retrieval metadata
- track source coverage and provider fallbacks
- return a normalized retrieval result contract

### 4.4 ExtractionAgent

Responsibilities:

- fetch page content for retrieved candidates
- apply browser fallback when needed
- perform structured extraction
- produce evidence-oriented normalized items for downstream evaluation

### 4.5 EvaluationAgent

Responsibilities:

- deduplicate extracted evidence items
- score them against business rules
- decide push vs skip
- build evaluation summary metrics for the run

EvaluationAgent owns business judgment, not final persistence.

## 5. Shared State Model

Keep the outer monitor run state, but reorganize it into explicit shared domains.

### 5.1 Global State Sections

#### run_context

Contains:

- `run_id`
- `topic_id`
- `topic`
- `trigger`
- `status`
- `errors`
- `events`

#### business_memory

Contains:

- `seed_keywords`
- `business_context`
- `push_history`
- `trusted_sources`
- optional degradation/history hints added by supervisor

#### planner_output

Contains:

- `expanded_queries`
- `query_plan`
- `source_plan`
- `retrieval_strategy`
- `planning_reasons`

#### retrieval_output

Contains:

- `candidate_pool`
- `source_coverage`
- `retrieval_failures`
- `provider_fallbacks`
- `tool_results`

#### extraction_output

Contains:

- `fetched_contents`
- `evidence_items`
- `extraction_failures`
- `content_fallbacks`

#### evaluation_output

Contains:

- `deduped_items`
- `scored_items`
- `final_decisions`
- `decision_reasons`
- `push_records`
- `eval_result`

## 6. Agent Contracts

### 6.1 PlannerAgent Contract

Input:

- `run_context`
- `business_memory`

Output:

- `planner_output`

### 6.2 RetrievalAgent Contract

Input:

- `run_context`
- `business_memory`
- `planner_output`

Output:

- `retrieval_output`

### 6.3 ExtractionAgent Contract

Input:

- `run_context`
- `planner_output`
- `retrieval_output`

Output:

- `extraction_output`

### 6.4 EvaluationAgent Contract

Input:

- `run_context`
- `business_memory`
- `planner_output`
- `retrieval_output`
- `extraction_output`

Output:

- `evaluation_output`

### 6.5 Contract Rule

Downstream agents may depend on upstream contracts, but may not depend on
upstream implementation details.

Example:

- Evaluation may consume `extraction_output.evidence_items`
- Evaluation must not assume retrieval was implemented specifically as
  `rss_fetch` followed by `mock_search`

## 7. LangGraph Orchestration

Replace the current fine-grained linear graph with stage-level agent nodes:

```text
start
  -> supervisor_bootstrap
  -> planner_agent
  -> retrieval_agent
  -> extraction_agent
  -> evaluation_agent
  -> supervisor_finalize
  -> end
```

### 7.1 supervisor_bootstrap

Responsibilities:

- mark run as active
- load push history
- initialize shared state sections
- write startup event

### 7.2 planner_agent

Internal responsibilities:

- retrieve business context
- expand keywords
- construct query and source planning outputs

### 7.3 retrieval_agent

Internal responsibilities:

- execute retrieval tools per plan
- unify candidate pool
- append retrieval events and fallback metadata

### 7.4 extraction_agent

Internal responsibilities:

- fetch raw content
- apply extraction
- emit evidence items

### 7.5 evaluation_agent

Internal responsibilities:

- deduplicate
- score
- decide push
- compute run-quality metrics

### 7.6 supervisor_finalize

Responsibilities:

- persist push records
- persist candidate/extracted/decision records
- persist events and eval result
- finalize status
- populate compatibility mirror fields

## 8. Compatibility Strategy

External APIs must remain stable during this refactor.

To preserve current routes and pages, keep legacy mirror fields during migration:

- `expanded_queries`
- `source_plan`
- `candidate_items`
- `fetched_contents`
- `extracted_items`
- `deduped_items`
- `scored_items`
- `final_decisions`
- `decision_reasons`
- `push_records`
- `eval_result`

Migration rule:

- specialist agents write new structured outputs
- supervisor finalization mirrors key values back into legacy top-level fields
- APIs continue reading the legacy fields until a later explicit API migration

## 9. Migration Mapping From Current Nodes

Map current nodes into agent-owned stages:

- `load_topic_node` -> `supervisor_bootstrap`
- `retrieve_business_context_node` -> `planner_agent`
- `expand_queries_node` -> `planner_agent`
- `plan_sources_node` -> `planner_agent`
- `retrieve_candidates_node` -> `retrieval_agent`
- `fetch_contents_node` -> `extraction_agent`
- `extract_structured_items_node` -> `extraction_agent`
- `deduplicate_items_node` -> `evaluation_agent`
- `score_items_node` -> `evaluation_agent`
- `decide_push_node` -> `evaluation_agent`
- `persist_push_records_node` -> `supervisor_finalize`
- `evaluate_run_node` -> `evaluation_agent` for scoring, then `supervisor_finalize`
  for persistence and status closure

## 10. Testing Strategy

Use TDD and split tests into two levels.

### 10.1 Agent Contract Tests

Add targeted tests for:

- PlannerAgent contract formation
- RetrievalAgent contract formation and fallback reporting
- ExtractionAgent evidence output formation
- EvaluationAgent decision/eval output formation

### 10.2 Supervisor Integration Tests

Preserve end-to-end tests for:

- full monitor run success
- compatibility top-level field population
- event chain completeness
- persisted records and eval output

## 11. Non-Goals

This refactor does not include:

- recursive replanning loops
- debate-style or reflection-style agent conversations
- distributed multi-process agent execution
- separate retrieval/extraction/evaluation queues
- external execution fabric redesign
- breaking the existing public API surface

## 12. Acceptance Criteria

This architecture work is complete only when:

1. the monitor graph is organized around supervisor plus specialist agent stages
2. planner outputs are topic/context/history aware rather than static
3. each specialist agent has a structured input/output contract
4. supervisor owns finalization and run lifecycle closure
5. current API responses still work through compatibility mirror fields
6. tests prove both agent contracts and end-to-end monitor behavior
