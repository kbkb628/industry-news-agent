# Project Scope Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove unfinished or abandoned extension artifacts so the repository matches the intended project presentation scope.

**Architecture:** Keep the working core project and completed resume-aligned capabilities. Remove abandoned roadmap pressure from docs first, then delete any dead code, config, tests, and README claims that exist only for removed slices. Finish with full verification so the repo remains truthful and runnable.

**Tech Stack:** Markdown docs, FastAPI backend, pytest, git

---

### Task 1: Audit Cleanup Targets

**Files:**
- Modify: `docs/superpowers/plans/2026-06-17-project-scope-cleanup.md`
- Inspect: `backend/README.md`
- Inspect: `docs/superpowers/specs/*.md`
- Inspect: `docs/superpowers/plans/*.md`
- Inspect: `backend/app/**/*.py`
- Inspect: `backend/tests/*.py`

- [ ] **Step 1: Record the concrete removal list**

Write down which abandoned slice artifacts will be deleted or rewritten:

- `docs/superpowers/plans/2026-06-17-industry-news-agent-phase2.md`
- abandoned slice plans under `docs/superpowers/plans/2026-06-17-*.md` except the original MVP plan
- abandoned slice specs under `docs/superpowers/specs/2026-06-17-*.md`
- any runtime files, tests, and README sections that are left orphaned by those deletions

- [ ] **Step 2: Inspect runtime references before deleting files**

Run:

```powershell
rg -n "onesearch|notification|playwright_mcp|opensearch|semantic dedup|eval judge|react dashboard|redis stream|worker governance" E:\bgagent2\.worktrees\feat-industry-news-mvp\backend E:\bgagent2\.worktrees\feat-industry-news-mvp\frontend E:\bgagent2\.worktrees\feat-industry-news-mvp\docs
```

Expected: identify all live references that must either be kept intentionally or removed together.

### Task 2: Remove Abandoned Planning And Spec Artifacts

**Files:**
- Delete: `docs/superpowers/plans/2026-06-17-eval-judge-adapter.md`
- Delete: `docs/superpowers/plans/2026-06-17-index-history-event-schema.md`
- Delete: `docs/superpowers/plans/2026-06-17-industry-news-agent-phase2.md`
- Delete: `docs/superpowers/plans/2026-06-17-notification-webhook.md`
- Delete: `docs/superpowers/plans/2026-06-17-onesearch-mcp-boundary.md`
- Delete: `docs/superpowers/plans/2026-06-17-openai-compatible-eval-judge.md`
- Delete: `docs/superpowers/plans/2026-06-17-opensearch-history-index.md`
- Delete: `docs/superpowers/plans/2026-06-17-playwright-mcp-browser-fetch.md`
- Delete: `docs/superpowers/plans/2026-06-17-quality-page-discoverability.md`
- Delete: `docs/superpowers/plans/2026-06-17-react-dashboard.md`
- Delete: `docs/superpowers/plans/2026-06-17-redis-stream-run-queue.md`
- Delete: `docs/superpowers/plans/2026-06-17-semantic-dedup.md`
- Delete: `docs/superpowers/plans/2026-06-17-worker-governance-event-schema.md`
- Delete: `docs/superpowers/specs/2026-06-17-onesearch-mcp-boundary-design.md`
- Delete: `docs/superpowers/specs/2026-06-17-react-dashboard-design.md`

- [ ] **Step 1: Delete abandoned spec and plan files**

Remove the files listed above because they keep non-core expansion as active repo direction.

- [ ] **Step 2: Keep only the MVP spec/plan and the cleanup spec/plan**

After deletion, `docs/superpowers/specs/` should keep:

- `2026-06-08-industry-news-agent-mvp-design.md`
- `2026-06-17-project-scope-cleanup-design.md`

And `docs/superpowers/plans/` should keep:

- `2026-06-08-industry-news-agent-mvp.md`
- `2026-06-17-project-scope-cleanup.md`

### Task 3: Remove Orphaned Runtime Surface

**Files:**
- Modify or Delete: runtime files discovered in Task 1 that are only justified by removed slices
- Modify: `backend/README.md`
- Modify: `frontend/src/App.tsx` if references to removed expansion framing remain
- Modify: `backend/app/**/*.py` if dead imports/config/tool wiring remain
- Modify: `backend/tests/*.py` if tests only cover removed slices

- [ ] **Step 1: Remove code paths that are now dead or misleading**

Delete runtime modules and config fields only when they no longer serve the kept
project surface after doc cleanup.

- [ ] **Step 2: Rewrite README to stop foregrounding abandoned expansion work**

Update `backend/README.md` so it describes the kept project surface only and no
longer centers abandoned Phase 2 expansion slices as the current state.

- [ ] **Step 3: Remove stale tests and references**

Delete or rewrite tests that cover only removed runtime surface. Keep tests for the
remaining project baseline.

### Task 4: Verify And Prepare Commit

**Files:**
- Modify: any remaining files touched by cleanup

- [ ] **Step 1: Run backend verification**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest -q
py -3.12 -m compileall app
```

Expected: all tests pass and app compiles.

- [ ] **Step 2: Run repo-level verification**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp
git diff --check
git status --short
```

Expected: no whitespace errors and only intentional cleanup changes remain.

- [ ] **Step 3: Commit cleanup milestone**

Commit with a message such as:

```bash
git add docs/superpowers/specs docs/superpowers/plans backend frontend
git commit -m "chore: remove abandoned expansion artifacts"
```
