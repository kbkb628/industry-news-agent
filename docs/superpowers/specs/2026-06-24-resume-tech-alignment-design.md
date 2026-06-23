# Resume Tech Alignment Design

## 1. Purpose

This document defines how the repository should be aligned with the explicit
technology choices written in the second resume project.

The goal is not to broaden the project scope. The goal is to make sure that
every technology explicitly named in the resume is backed by a real
implementation path in the repository, and that future feature work is built on
top of that real path instead of on top of mock-only or boundary-only layers.

This design freezes two rules:

1. Existing resume-listed technologies that are not fully real yet must be
   completed first.
2. New feature work must be designed against future real deployments, even if
   a temporary mock or compatibility layer still exists during the transition.

## 2. Scope

This design only covers the technologies explicitly named in the resume entry
for the industry-news structured push agent.

In-scope technologies:

- `FastAPI`
- `LangGraph`
- `MCP`
- `RAG`
- `Playwright`
- `PostgreSQL`
- `Redis`
- `Elasticsearch`
- `APScheduler`
- `Redis Stream`

Out of scope for this design:

- technologies that appear only in `README.md`, backend docs, or internal code
  but are not explicitly named in the resume
- cosmetic showcase upgrades that do not change technical truth
- new provider integrations that are unrelated to a resume-listed technology
- changing the resume wording to hide technical gaps instead of addressing them

## 3. Alignment Standard

A resume-listed technology is considered aligned only when all of the following
are true:

1. There is a real code path using that technology.
2. There is a real configuration entry explaining how the capability is enabled.
3. There is a real runnable flow inside the project that exercises it.
4. There is verification evidence such as tests, API responses, persistent
   records, run logs, or visible admin/dashboard output.
5. Failure and degradation behavior are explicit, and do not silently convert a
   mock or fallback path into a fake success.

The following do not count as alignment:

- interface-only adapters with no verified runtime
- compatibility shims presented as if they were full deployments
- documentation claims with no matching code path
- mock-only execution presented as the actual selected technology

## 4. Current Truth Boundary

This section classifies current alignment conservatively.

### 4.1 Already Substantially Real

- `FastAPI`
  - Real API and HTML surfaces exist.
  - Real routes, request/response handling, tests, and startup flow exist.

- `PostgreSQL`
  - Real persistence exists for long-lived business records.
  - It already functions as the factual storage layer for runs, pushes, events,
    and related entities.

- `Redis`
  - Real short-lived coordination exists.
  - Redis-backed execution and in-memory fallback are already implemented, but
    the repository still needs clearer proof that Redis-owned responsibilities
    are stable and intentionally bounded.

- `LangGraph`
  - Real in-process multi-agent orchestration exists.
  - However, some upstream capabilities consumed by the graph remain partial or
    boundary-level, which weakens the truth level of the whole narrative.

- `APScheduler`
  - Real scheduled execution exists.
  - It still needs stronger evidence and tighter integration with the final
    queue model that the resume implies.

### 4.2 Partial

- `RAG`
  - Real business-context retrieval exists, but the current implementation is
    narrower than the resume wording.
  - The resume wording implies a fuller retrieval stack than the current local
    lightweight retrieval path proves.

### 4.3 Boundary Or Not Yet Sufficiently Proven

- `MCP`
  - The repo has gateway and compatibility boundaries, but not yet a verified
    end-to-end real MCP-backed run path that should be treated as resume-grade.

- `Playwright`
  - The repo has a Playwright-compatible fallback boundary, but not yet a
    verified real browser-backed capture path that can be treated as delivered.

- `Elasticsearch`
  - The repo has an OpenSearch-compatible history/index boundary, but not yet a
    verified real search index layer that should count as a delivered
    technology choice.

- `Redis Stream`
  - Queue-oriented concepts exist, but the full resume-grade stream ownership,
    consumer-group flow, retry semantics, and verification evidence are not yet
    complete enough.

## 5. Design Principles

### 5.1 Engineering Dependency Order Wins

Implementation order follows engineering dependency order, not presentation
order and not interview-risk order.

Reason:

- upper-layer features become fragile if state, queue, and retrieval
  infrastructure are still provisional
- visible demo evidence is less valuable if it sits on top of temporary
  execution paths
- this order minimizes rework

### 5.2 Function Before Showcase

The project should first become technically true, then visually persuasive.

Admin pages, dashboard wording, and resume-evidence pages are useful, but they
must describe real working paths rather than compensate for missing ones.

### 5.3 Mocks May Exist Temporarily, But Must Not Own The Final Contract

Temporary mocks are allowed when they help stage a migration, but future
implementation contracts must be designed for the real target technology.

Examples:

- `MockLLM` may remain during feature evolution, but state structure and agent
  contracts must support the eventual real retrieval and tool paths
- a local gateway may remain as a compatibility layer, but the project must not
  pretend that this equals a real `MCP` deployment

### 5.4 PostgreSQL Remains The Business Source Of Truth

Even after search and queue layers are strengthened:

- `PostgreSQL` owns durable business facts
- `Redis` and `Redis Stream` own short-lived coordination
- `Elasticsearch` owns derived retrieval and indexing surfaces

No derived layer may become the only durable record of business outcomes.

## 6. Phase Structure

### 6.1 Phase A: Complete Existing Resume Technologies To Real Runtime Level

This phase upgrades already-present but not fully proven technologies to a real
runtime level.

The sequence is:

1. `PostgreSQL`
2. `Redis`
3. `APScheduler`
4. `Redis Stream`
5. `Elasticsearch`
6. `MCP`
7. `Playwright`
8. `RAG`
9. `LangGraph` contract tightening after the lower layers are made real

### 6.2 Phase B: Build Missing Project Capabilities On Top Of The Realized Stack

After Phase A, continue feature work for the resume project using the real
infrastructure and integration model as the default assumption.

This phase does not introduce throwaway demo-only contracts.

### 6.3 Phase C: Evidence And Narrative Closure

Only after the technical stack is sufficiently real:

- tighten docs
- tighten API-visible evidence
- tighten admin/dashboard proof surfaces
- tighten interview-safe wording

This phase explains reality. It does not replace reality.

## 7. Phase A Technical Checklist

### 7.1 PostgreSQL

Target:

- confirm and enforce `PostgreSQL` as the durable source of truth for topics,
  monitor runs, candidates, structured extraction results, decisions, push
  records, events, and evaluation results

Must be true at completion:

- schema ownership is explicit
- startup and configuration clearly require or intentionally wire PostgreSQL
- the repository layer uses PostgreSQL as the durable business store
- verification proves writes and reads for every major business entity

Evidence must include:

- tests
- real persisted records
- API or admin readback

### 7.2 Redis

Target:

- confirm and harden `Redis` as the short-lived coordination layer

Must be true at completion:

- active-run locks are real
- short-lived dedup keys are real
- transient coordination state is real
- Redis failure behavior is explicit and does not corrupt PostgreSQL facts

Evidence must include:

- tests for lock/dedup behavior
- logs or events proving Redis-assisted coordination

### 7.3 APScheduler

Target:

- convert scheduling from a truthful feature into a clearly managed runtime
  capability

Must be true at completion:

- topic-bound jobs are registered intentionally
- scheduler startup/shutdown ownership is clear
- duplicate or conflicting scheduling behavior is controlled
- scheduler-triggered runs are visible through events and persisted run records

Evidence must include:

- scheduler integration tests or controlled runtime verification
- visible run/event evidence for scheduled triggers

### 7.4 Redis Stream

Target:

- align queued execution with the resume claim of `Redis Stream`

Must be true at completion:

- scheduler produces tasks into a real stream-backed queue path
- consumer-group based workers consume from the stream
- ack and retry behavior are explicit
- failure handling is traceable
- queue state is not only simulated in memory when the stream path is selected

Evidence must include:

- worker tests
- stream processing logs or events
- end-to-end queued run verification

### 7.5 Elasticsearch

Target:

- deliver a real derived search/index layer instead of only an OpenSearch-style
  boundary

Must be true at completion:

- documents are projected into a real index
- index mapping and indexing ownership are explicit
- query paths use the real search layer
- projection failure behavior is explicit
- PostgreSQL remains the durable source of truth

Evidence must include:

- indexing verification
- retrieval verification
- reconciliation or backfill path definition

### 7.6 MCP

Target:

- upgrade `MCP` from gateway-only narrative to a real integrated capability

Must be true at completion:

- at least one real MCP-backed runtime path is configured and executable
- tool discovery or equivalent session setup is real
- tool invocation results are normalized into project contracts
- timeout, error, and fallback behavior are visible

Evidence must include:

- a runnable configured path
- logs or events showing real MCP-backed calls
- at least one end-to-end monitor flow using that path

### 7.7 Playwright

Target:

- deliver a real browser-backed retrieval or fallback path

Must be true at completion:

- real Playwright-backed page access is integrated
- domain allowance and timeout controls are explicit
- browser usage is governed rather than unconstrained
- the browser path contributes real extraction evidence

Evidence must include:

- controlled test or runtime verification
- event/log proof of browser-backed fetch or extraction

### 7.8 RAG

Target:

- align `RAG` with the resume wording using a real business-knowledge retrieval
  flow rather than only a narrow local helper

Must be true at completion:

- the knowledge base is real and intentionally structured
- retrieval writes business context back into agent state
- retrieval affects planning, retrieval, evaluation, or dedup decisions
- the implementation path is broader than pure keyword lookup

The target direction should support:

- `embedding`
- `BM25`
- `rerank`

This does not require all final sophistication in one step, but the resulting
design must clearly move toward the resume wording instead of away from it.

Evidence must include:

- retrieval tests
- run-state evidence
- visible proof that retrieved context changed agent behavior

### 7.9 LangGraph

Target:

- after the lower layers are made real, tighten `LangGraph` contracts so the
  multi-agent narrative rests on real capability boundaries

Must be true at completion:

- planner, retrieval, extraction, and evaluation contracts are stable
- agent state semantics match the real infrastructure beneath them
- the graph no longer depends on fake or overstated upstream capabilities

Evidence must include:

- contract tests
- integration tests
- visible run-state evidence

## 8. Phase B Functional Expansion Rules

After Phase A, new feature work must follow these rules:

1. New features must build on the real infrastructure path selected in Phase A.
2. New state fields and API contracts must assume the real technology path, not
   the temporary mock path.
3. A temporary fallback may remain, but it must be clearly labeled and must not
   become the silent default if that would weaken the truth of a resume-listed
   technology.
4. No new feature may introduce a fake queue, fake retrieval layer, fake search
   projection, or fake browser execution path.

## 9. Phase C Evidence Closure

Each resume-listed technology must eventually have a mapped proof bundle:

- code path
- config entry
- runtime trigger path
- verification result
- API/admin/dashboard evidence

The repository should make it easy to answer:

- where this technology is used
- how it is enabled
- how it behaves on success
- how it behaves on failure
- what evidence proves it is real

## 10. Non-Goals

This design does not require:

- immediate distributed deployment
- immediate replacement of every mock in the repository
- unrelated new providers
- non-resume technologies being upgraded just because the code already has an
  adapter
- doing showcase polish before the technical path becomes true

## 11. Acceptance Criteria

This design is successfully implemented only when:

1. every in-scope resume technology has been classified and assigned an
   implementation target
2. implementation sequencing follows engineering dependency order
3. `PostgreSQL`, `Redis`, `APScheduler`, and `Redis Stream` are not merely
   mentioned, but verifiably own their intended runtime responsibilities
4. `Elasticsearch`, `MCP`, `Playwright`, and `RAG` are upgraded from partial or
   boundary-level narratives into real runnable project capabilities
5. `LangGraph` contracts are tightened only after the lower layers become real
6. future feature work is constrained to build on the realized stack rather
   than on throwaway mock-only paths
7. docs and demo surfaces are updated after, not instead of, technical truth
