# Industry News Agent Phase 2 Plan

## Goal

Extend the completed MVP toward the fuller project shape described in the resume entry for "行业资讯结构化推送智能体", while preserving the working MVP baseline already merged to `main`.

This phase does not restart the project. It builds on the verified MVP that already provides:

- topic CRUD APIs
- monitor run orchestration through LangGraph
- mock retrieval / fetch / extract / dedup / score / push decision flow
- monitor run, push, event, and eval persistence
- minimal HTML admin pages
- full backend test coverage for the MVP closed loop

## Why A New Phase

The current MVP is complete against `DEVELOPMENT_GUIDE.md`, but the resume project description claims additional engineering capabilities that are not yet implemented in code:

- real scheduled execution instead of scheduler bootstrap only
- Redis Stream queue and worker execution
- concurrency / timeout / backpressure controls
- real MCP / browser / search provider integrations
- hybrid RAG with embedding + BM25 + rerank
- richer business memory and quality observability

This document turns those gaps into an execution plan.

## Delivery Strategy

Follow staged delivery. Do not chase the full resume surface area at once. Build one truthful, end-to-end extension at a time.

The first slice must be:

`topic schedule -> queue enqueue -> worker execute run -> persisted run result`

That slice is the highest-leverage upgrade because it closes the largest gap between the MVP and the resume claims.

## Non-Goals For The First Slice

The first slice does not include:

- real Playwright or MCP browser execution
- external search providers beyond current MVP tools
- embedding retrieval or rerank
- React dashboard
- notification delivery channels
- full production deployment packaging

## Phase Breakdown

### Phase 2A: Scheduler And Worker Execution

Target outcome:

- topics can register actual scheduler jobs
- scheduler trigger enqueues a run request
- worker consumes queued run requests
- worker executes the monitor graph and persists results
- the system distinguishes manual runs from scheduled runs

Scope:

- add queue abstraction with Redis-backed and in-memory implementations
- add run trigger source fields
- add scheduler registration service
- add worker execution service
- add tests for enqueue, dequeue, and end-to-end scheduled execution

Acceptance evidence:

- backend tests prove a scheduled topic produces a persisted monitor run through the worker path
- backend tests prove queue fallback still works without live Redis

### Phase 2B: Concurrency Governance

Target outcome:

- queue and worker processing have bounded concurrency, timeout, and retry rules
- run duplication for the same topic is prevented during active execution

Scope:

- topic-level run lock
- worker timeout handling
- retry metadata
- queue/backpressure metrics in persisted events

### Phase 2C: Real Tool Integrations

Target outcome:

- at least one real search provider is integrated
- browser fallback path is explicit and controlled
- local mock tools remain available for deterministic tests

Scope:

- search provider abstraction
- real provider implementation
- browser fallback abstraction
- event logging for provider choice and fallback path

### Phase 2D: Hybrid RAG

Target outcome:

- business context retrieval supports more than keyword matching

Scope:

- BM25 retrieval
- embedding retrieval
- rerank
- trusted source and push-history knowledge participation

### Phase 2E: Richer Memory And Observability

Target outcome:

- business entities are persisted beyond run snapshots
- quality metrics support trend analysis

Scope:

- candidate persistence
- extracted-item persistence
- structured decision persistence
- richer eval metrics
- quality summary endpoints/pages

## First Implementation Slice

The next implementation work in this branch is only `Phase 2A`.

### Files Expected To Change

- `backend/app/scheduler/jobs.py`
- `backend/app/scheduler/worker.py`
- `backend/app/main.py`
- `backend/app/api/topics.py`
- `backend/app/storage/repository.py`
- `backend/tests/test_topics_api.py`
- `backend/tests/test_monitor_run_flow.py`
- additional focused scheduler/worker tests if needed

### Contracts To Freeze Before Coding

- topic registration must remain explicit through existing topic records
- queue payload shape must at least include `topic_id`, `trigger`, and enqueue timestamp
- worker execution must preserve the existing monitor graph persistence behavior
- queue fallback must remain truthful: no fake background completion signals

### Initial Acceptance Criteria

- creating a scheduled topic registers a job in the scheduler service
- triggering the scheduler path enqueues a run request
- consuming the queued request produces a persisted monitor run
- manual execution still works
- all existing MVP tests remain green

## Verification Plan

- run focused scheduler/worker tests during development
- run full backend test suite before claiming the slice is done
- perform spec review first, then code quality review

## Git Plan

- keep `main` stable
- implement this phase on `feat/phase2-scheduler-worker`
- commit the plan before implementation
- commit the working slice only after tests and reviews pass
