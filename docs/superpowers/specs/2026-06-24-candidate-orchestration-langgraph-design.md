# Candidate Orchestration LangGraph Design

## 1. Purpose

This document defines how the project should upgrade from stage-only execution
into real candidate-level orchestration while staying aligned with the resume
and `DEVELOPMENT_GUIDE.md`.

The goal is not to introduce a new distributed workflow engine. The goal is to
make the existing LangGraph-based monitor flow truthfully support:

- source-level planning
- candidate-level task splitting
- limited same-stage concurrency in a single process
- Redis-owned short-lived coordination
- PostgreSQL-backed task history and business evidence

This design is intentionally scoped to the current project phase. It must make
multi-agent coordination more real without drifting away from the documented
strategy.

## 2. Why This Change Exists

The current repository already has:

- `planner`, `retrieval`, `extraction`, and `evaluation` role boundaries
- a LangGraph monitor flow
- PostgreSQL durable business storage
- Redis and Redis Stream runtime coordination foundations

However, the current execution path is still mostly stage-serial:

- planner builds a plan
- retrieval returns a batch of candidates
- later stages process collections in bulk

This is not yet the strongest implementation match for the resume expression
that the system:

- breaks work into planning, retrieval, page access, structured extraction, and
  value scoring stages
- uses Redis for task locks and runtime state
- uses PostgreSQL for history and traceability
- supports multi-agent coordination rather than only named stage wrappers

The next truthful step is therefore not a fully distributed DAG engine, but a
candidate-level orchestrator inside the existing LangGraph skeleton.

## 3. Scope

In scope:

- keep `planner_agent` responsible for source-level planning
- keep `retrieval_agent` responsible for source task execution
- introduce candidate-level task orchestration after retrieval
- support same-stage limited concurrency inside one process
- persist task ledger facts in PostgreSQL
- keep short-lived task runtime state in Redis and run state semantics
- preserve current business result tables and API shapes where possible

Out of scope:

- distributed workers for candidate tasks
- replacing LangGraph with a separate workflow product
- adding cross-process task claiming for candidate tasks in this slice
- redesigning frontend/admin pages in this slice
- forcing all transient task heartbeats into PostgreSQL
- introducing a new resume technology not already stated in the resume

## 4. Guiding Rules

### 4.1 Resume Alignment First

When implementation choices are ambiguous, prefer the path that best matches:

- the explicit resume technology wording
- the role split in `DEVELOPMENT_GUIDE.md`
- the existing truth boundary already established in Phase A

### 4.2 PostgreSQL Owns Durable Facts

PostgreSQL remains the durable source of truth for:

- topics
- monitor runs
- candidates
- extracted items
- decisions
- push records
- run events
- eval results
- candidate task ledger facts introduced by this design

PostgreSQL does not become the high-frequency in-flight scheduler state store.

### 4.3 Redis Owns Short-Lived Coordination

Redis and run-local runtime state own:

- in-flight task tracking
- concurrency slot control
- short-lived task locks
- transient retry coordination
- non-durable runtime counters

If Redis degrades or is unavailable, the runtime may fall back to a narrower
single-process behavior, but durable business facts and durable task evidence
must still be preserved in PostgreSQL.

### 4.4 LangGraph Remains The Top-Level Orchestration Backbone

LangGraph still owns the main run lifecycle. Candidate-level concurrency is
added inside a bounded orchestration node rather than by exploding the graph
into dozens of micro-nodes.

This keeps the graph truthful and understandable:

- graph nodes express major stage transitions
- candidate orchestrator expresses real task progression within the run

## 5. Target Architecture

### 5.1 Top-Level Flow

The monitor flow becomes:

1. `supervisor_bootstrap`
2. `planner_agent`
3. `retrieval_agent`
4. `candidate_task_orchestrator`
5. `supervisor_finalize`

`extraction_agent` and `evaluation_agent` remain real modules, but they no
longer sit only as top-level batch-processing graph nodes. Instead, they become
worker roles consumed by the candidate orchestrator.

### 5.2 Source-Level Planning Stays In Planner

`planner_agent` remains responsible for:

- `expanded_queries`
- `query_plan`
- `source_plan`
- `retrieval_strategy`
- `planning_reasons`

It does not generate candidate tasks before retrieval. Candidate tasks are
created only after real candidates exist.

### 5.3 Retrieval Stays Source-Oriented

`retrieval_agent` executes the planned source tasks and produces:

- `candidate_pool`
- source coverage evidence
- retrieval failure evidence
- provider fallback evidence

This stage is the boundary where orchestration focus changes:

- before retrieval: tasks are source-oriented
- after retrieval: tasks are candidate-oriented

### 5.4 Candidate Orchestrator Becomes The Core Runtime Addition

The new `candidate_task_orchestrator` is responsible for:

- creating candidate tasks from retrieved candidates
- executing same-stage tasks with bounded concurrency
- enforcing per-candidate stage dependencies
- routing task work to worker agents
- recording task runtime state and durable task evidence
- aggregating outputs back into the existing run result structures

## 6. Candidate Task Model

### 6.1 Task Stages

This slice introduces three candidate task stages:

- `fetch`
- `extract`
- `evaluate`

The progression rule is strict:

- a candidate must complete `fetch` before `extract`
- a candidate must complete `extract` before `evaluate`

This slice does not introduce cross-stage speculative execution.

### 6.2 Task Statuses

Each task has one of the following statuses:

- `pending`
- `ready`
- `in_progress`
- `completed`
- `failed`
- `skipped`

The status model is intentionally simple so it is easy to test and reason
about.

### 6.3 Task Fields

Each task should be represented through one stable contract with fields like:

- `task_id`
- `run_id`
- `candidate_id`
- `stage`
- `status`
- `attempt`
- `max_attempts`
- `depends_on_task_ids`
- `input_ref`
- `output_ref`
- `error_code`
- `error_message`
- `started_at`
- `finished_at`

`input_ref` and `output_ref` should point to existing run-state entities or
persisted business entities rather than duplicating large payloads inside the
task row.

## 7. State Model Changes

### 7.1 Existing Result Fields Stay

The following run-state result fields remain the authoritative result surfaces:

- `candidate_items`
- `fetched_contents`
- `extracted_items`
- `scored_items`
- `final_decisions`
- `push_records`
- `eval_result`

The orchestrator fills these fields through real task execution instead of a
single bulk pass.

### 7.2 New Run-State Orchestration Fields

The run state should add orchestration-focused fields:

- `candidate_task_plan`
- `candidate_task_runtime`
- `candidate_task_summary`

Recommended meanings:

- `candidate_task_plan`: the run-level task snapshot created by the
  orchestrator
- `candidate_task_runtime`: current runtime view such as ready/in-progress
  counts and per-stage slot usage
- `candidate_task_summary`: final summary counts and failure totals at run end

These fields support truthful run-state evidence without replacing the existing
business result fields.

## 8. PostgreSQL Task Ledger

### 8.1 Purpose

The new task ledger exists to prove how candidate-level work progressed. It is
not a high-frequency heartbeat stream and not a replacement for business result
tables.

### 8.2 Durable Facts To Persist

The task ledger should persist:

- `task_id`
- `run_id`
- `candidate_id`
- `stage`
- final or latest durable `status`
- `attempt`
- `max_attempts`
- `error_code`
- `error_message`
- result references such as output candidate/extracted/decision ids
- `created_at`
- `started_at`
- `finished_at`

### 8.3 Facts That Should Not Be Persisted Aggressively

The task ledger should not be used for:

- microsecond-level scheduling traces
- per-thread slot churn
- internal polling loops
- every ephemeral coordination mutation

Those belong to runtime coordination, not to durable business truth.

### 8.4 Relationship To Existing Tables

The task ledger complements rather than replaces:

- candidates
- extracted items
- decisions
- push records
- run events
- eval results

The business tables answer "what business result was produced." The task ledger
answers "how candidate-level work progressed to produce that result."

## 9. Runtime Coordination Model

### 9.1 Same-Stage Limited Concurrency

The orchestrator should allow bounded same-stage concurrency, for example:

- `fetch` concurrency limit `N`
- `extract` concurrency limit `M`
- `evaluate` concurrency limit `K`

These limits must come from configuration, not be hard-coded.

### 9.2 Single-Process Controlled Scheduling

This slice stays single-process for candidate orchestration.

Implementation direction:

- main LangGraph run remains in-process
- candidate orchestrator uses a bounded internal executor
- concurrency is controlled rather than opportunistic

This is enough to make real candidate-level coordination true without adding
distributed complexity too early.

### 9.3 Redis-Backed Short-Lived Coordination

Redis may be used for:

- short-lived task locks
- runtime counters
- retry coordination markers
- active in-flight ownership signals

If Redis is unavailable, degraded local runtime coordination may still proceed,
but the system must preserve durable task and business facts in PostgreSQL and
must not silently pretend the stronger runtime guarantee still exists.

## 10. Worker Role Responsibilities

### 10.1 Extraction Agent

`extraction_agent` should expose task-oriented worker entry points instead of
only full-batch behavior. It should support at least:

- fetch task execution
- extract task execution

This turns it into a real worker role inside the orchestrator.

### 10.2 Evaluation Agent

`evaluation_agent` should support candidate-level evaluation task execution
rather than only run-wide batch scoring semantics.

It should return:

- candidate score
- push/no-push decision
- decision reason
- evaluation failure evidence when needed

### 10.3 Planner And Retrieval Agent Responsibilities Stay Narrow

`planner_agent` should remain planning-focused.

`retrieval_agent` should remain source-task-focused.

The orchestrator should not silently absorb their responsibilities because that
would weaken the explicit multi-agent boundaries the resume relies on.

## 11. Error And Retry Semantics

### 11.1 Failure Categories

Task failures should be normalized into at least these categories:

- `tool_error`
- `content_error`
- `governance_error`

Examples:

- `tool_error`: MCP call failure, search timeout, browser fetch failure
- `content_error`: empty page content, extraction payload invalid
- `governance_error`: dependency violation, retry budget exhausted,
  coordination inconsistency

### 11.2 Stage-Specific Retry Guidance

Recommended retry direction:

- `fetch`: allow limited retries because external fetching is unstable
- `extract`: allow fewer retries; do not repeatedly retry obviously empty input
- `evaluate`: allow minimal retries, mainly for transient tool/provider errors

The runtime coordination layer owns short-lived retry scheduling. PostgreSQL
owns the durable retry conclusion.

### 11.3 Run Outcome Behavior

A single candidate task failure must not automatically collapse the whole run
into an uninformative global failure. The run should preserve:

- which candidate failed
- at what stage it failed
- whether it was retried
- whether the rest of the run still completed meaningfully

This is important for truthful operational evidence and interview explanation.

## 12. Event And Trace Evidence

Run events should become more explicit about candidate orchestration while
avoiding noise.

Good evidence events include:

- orchestrator started
- fetch stage batch completed
- extract stage batch completed
- evaluate stage batch completed
- retry budget exhausted for a candidate task
- task orchestration completed with summary counts

Bad evidence would be event floods for every micro-scheduling tick.

The trace goal is explainability, not event volume.

## 13. Verification Requirements

### 13.1 Unit Tests

Add tests that prove:

- planner still produces real source-level plans
- orchestrator creates candidate tasks from retrieved candidates
- task dependency progression is correct
- same-stage concurrency never exceeds configured limits
- retries and final failure semantics are correct

### 13.2 Integration Tests

Add tests that prove a monitor run can produce:

- retrieved candidate pool
- candidate task ledger entries
- fetched contents
- extracted items
- final decisions
- run summary evidence

Add failure-path tests showing:

- one candidate can fail while others complete
- durable task evidence remains queryable
- no fake success is emitted for failed candidate tasks

### 13.3 Persistence Verification

Add repository and API-level verification that PostgreSQL can read back:

- task ledger entries by run
- task ledger entries by candidate
- task summary evidence tied to a run

### 13.4 Evidence Closure

The implementation should make it easy to show:

- where candidate-level orchestration happens
- how Redis participates in runtime coordination
- how PostgreSQL proves durable task and business history
- how worker failures and retries are explained

## 14. Non-Goals For This Slice

This slice does not require:

- external distributed task runners
- a general-purpose DAG engine
- a new frontend visualization page
- full MCP or Playwright stage-two integrations to be finished immediately
- replacing all existing batch helper functions at once if a narrower bridge is
  safer during migration

## 15. Acceptance Criteria

This design is successfully implemented only when all of the following are
true:

1. source-level planning remains real and explicit
2. retrieval still executes real source tasks rather than a hard-coded path
3. candidate-level `fetch`, `extract`, and `evaluate` tasks are created and
   progressed through a real orchestrator
4. same-stage bounded concurrency is real inside one process
5. Redis or equivalent short-lived runtime coordination is explicit
6. PostgreSQL stores candidate task durable evidence in addition to business
   result facts
7. run-state evidence clearly shows task plan, runtime summary, and final
   summary
8. failure, retry, and degradation behavior are explicit and testable
9. the implementation remains inside the strategy boundary defined by the
   resume and `DEVELOPMENT_GUIDE.md`
