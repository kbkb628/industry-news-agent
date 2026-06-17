# Project Scope Cleanup Design

## 1. Purpose

This document freezes the cleanup scope for the current repository so the codebase
matches the user's stated delivery goal:

- keep completed, resume-aligned project capabilities
- remove unfinished or abandoned extension work and all related artifacts
- keep the repository clean for project presentation

This cleanup does not broaden product scope and does not introduce new features.

## 2. Cleanup Principle

The repository should keep only capabilities that satisfy all of the following:

1. they are already implemented and runnable
2. they support the resume narrative for the second project
3. the user is willing to keep them as part of the project presentation

Anything that is unfinished, abandoned, or only documented as a future extension
must be removed together with:

- runtime code
- configuration surface
- tests
- README claims
- internal spec and plan documents

## 3. Keep Boundary

The following areas remain in scope and must be preserved:

- FastAPI backend closed loop
- LangGraph monitor flow
- topic, run, candidate, push, event, and eval APIs
- PostgreSQL and Redis backed runtime
- MockLLM-based main loop with replaceable interfaces
- local knowledge-base and business-context retrieval
- candidate retrieval, content fetch, extraction, dedup, scoring, push decision
- persisted run records, candidate records, extracted records, decision records
- trace events and quality metrics
- minimal HTML pages that support project demonstration

Completed optional capabilities may remain if they are already working and do not
create misleading unfinished branches.

## 4. Remove Boundary

The following content must be removed if it represents unfinished or abandoned
extension direction rather than a capability the project will continue to present:

- unfinished provider-specific notification direction
- future-oriented roadmap documents that keep pushing non-core expansion
- spec and plan documents for abandoned slices
- README and in-repo documentation that foreground abandoned extension work
- dead config flags, imports, tests, and tool registration tied only to removed
  abandoned slices

## 5. Initial Cleanup Target Set

Based on the current audit, the first cleanup target set is:

- Phase 2 roadmap documents that continue driving post-MVP expansion
- notification-specific spec/plan artifacts that are no longer part of the
  intended development path
- abandoned expansion planning artifacts for OneSearch boundary, Playwright MCP,
  OpenSearch history projection, eval-judge expansion, semantic dedup, React
  dashboard expansion, worker/governance extension, and Redis Stream expansion,
  where those artifacts serve roadmap pressure rather than current project
  presentation

The implementation step must verify whether any runtime code is only justified by
those artifacts and remove it if it is now dead or misleading.

## 6. Non-Goals

This cleanup does not:

- rewrite `DEVELOPMENT_GUIDE.md`
- delete completed core project code just because it is optional
- reduce the system below the already working project presentation baseline
- introduce a new architecture direction

## 7. Acceptance Criteria

Cleanup is complete when:

1. no abandoned extension slice remains as an active roadmap in repo docs
2. removed slices have no stale code/config/test references left behind
3. README reflects only the intended kept project surface
4. tests still pass after the cleanup
