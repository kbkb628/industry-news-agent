# Resume Alignment Showcase Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the repository, project presentation, and demo surfaces more tightly with the resume wording for the industry-news structured push agent without inventing unimplemented capabilities.

**Architecture:** Keep the current truthful backend core and real multi-agent monitor flow. Add a thin presentation layer around it: explicit resume-to-code evidence documentation, clearer showcase-oriented admin pages, and a stronger dashboard narrative for multi-agent orchestration, queue governance, and evaluation visibility. Do not broaden provider scope unless the capability is already implemented and runnable.

**Tech Stack:** Markdown docs, FastAPI, Jinja2 templates, React + Vite, pytest, Vitest, TypeScript

---

### Task 1: Freeze Resume Alignment Assets

**Files:**
- Create: `PROJECT_TODO.md`
- Create: `docs/resume-alignment.md`
- Modify: `README.md`
- Modify: `backend/README.md`

- [ ] **Step 1: Write the failing documentation expectation list**

Record the assets that must exist after this task:

```text
1. A repository-level TODO document with pending / in_progress / completed sections
2. A resume-alignment document that maps each resume claim to:
   - code files
   - API endpoints
   - demo pages
   - current claim status (ready / partial / future boundary)
3. Root and backend README wording updated to reference the resume-alignment doc
```

- [ ] **Step 2: Inspect current docs before editing**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp
Get-Content -Raw README.md
Get-Content -Raw backend\README.md
```

Expected: current docs describe the implemented architecture, but do not yet provide a concise resume-claim-to-evidence map.

- [ ] **Step 3: Write the TODO and evidence docs**

Create `PROJECT_TODO.md` with:

```markdown
# Project TODO

## pending
- polish showcase pages for resume-aligned demo flow
- tighten dashboard wording around multi-agent orchestration and governance
- verify final repository presentation and commit milestone

## in_progress
- resume-alignment showcase work

## completed
- truthful MVP closed loop
- scheduler and worker governance flow
- real in-process multi-agent architecture
- project documentation alignment
```

Create `docs/resume-alignment.md` with sections:

- `Resume Claim Snapshot`
- `Claim To Code Evidence`
- `Ready To Say In Interview`
- `Partial / Boundary Claims`
- `Suggested Demo Order`

For each major resume claim, explicitly map to files such as:

- `backend/app/agent/graph.py`
- `backend/app/agent/planner_agent.py`
- `backend/app/agent/retrieval_agent.py`
- `backend/app/agent/extraction_agent.py`
- `backend/app/agent/evaluation_agent.py`
- `backend/app/scheduler/worker.py`
- `backend/app/eval/rule_scorer.py`
- `backend/app/api/*`

- [ ] **Step 4: Update README entry points**

Add short references in `README.md` and `backend/README.md` pointing readers to:

- `docs/resume-alignment.md`
- `PROJECT_TODO.md`

The wording must clearly say the document maps resume wording to implemented code and highlights truth boundaries.

- [ ] **Step 5: Run focused verification**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp
git diff --check
```

Expected: no whitespace errors.

- [ ] **Step 6: Commit**

```bash
git add PROJECT_TODO.md docs/resume-alignment.md README.md backend/README.md
git commit -m "docs: add resume alignment evidence map"
```

### Task 2: Upgrade HTML Admin Pages For Showcase Readability

**Files:**
- Modify: `backend/app/templates/base.html`
- Modify: `backend/app/templates/topics.html`
- Modify: `backend/app/templates/run_detail.html`
- Modify: `backend/app/templates/events.html`
- Modify: `backend/app/templates/pushes.html`
- Modify: `backend/app/templates/quality.html`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_health_api.py`

- [ ] **Step 1: Write the failing page expectations**

Add a backend test that asserts the HTML pages now contain showcase-oriented copy:

```python
def test_html_pages_include_showcase_navigation(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Resume Showcase" in response.text
    assert "Multi-Agent Pipeline" in response.text
```

- [ ] **Step 2: Run the targeted test to verify failure**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_health_api.py -q
```

Expected: FAIL because the current templates do not contain the new showcase copy.

- [ ] **Step 3: Implement showcase-oriented page templates**

Update the templates so the minimal HTML admin pages become a coherent demo surface:

- `base.html`
  - add a clear project title
  - add navigation labels for topics, pushes, quality, and resume alignment
- `topics.html`
  - explain that topics define monitor intent and scheduling
- `run_detail.html`
  - explain the run lifecycle and compatibility snapshot
- `events.html`
  - explain trace/governance events and what viewers should look for
- `pushes.html`
  - explain push decisions and persistence
- `quality.html`
  - explain quality metrics, fallback counts, and evaluation purpose

Keep the pages simple, server-rendered, and truthful.

- [ ] **Step 4: Add a resume-alignment page route**

In `backend/app/main.py`, add:

- `GET /resume-alignment`

Render a new template or reuse a simple template that links users to the resume-alignment doc summary in page form. If a new template is needed, create:

- `backend/app/templates/resume_alignment.html`

- [ ] **Step 5: Run targeted backend tests**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_health_api.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/main.py backend/app/templates backend/tests/test_health_api.py
git commit -m "feat: improve html showcase pages"
```

### Task 3: Strengthen React Dashboard Narrative

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/App.test.tsx`

- [ ] **Step 1: Write failing dashboard expectations**

Update `frontend/src/App.test.tsx` with expectations for:

```tsx
expect(await screen.findByText(/Supervisor -> Planner -> Retrieval -> Extraction -> Evaluation/i)).toBeInTheDocument();
expect(await screen.findByText(/Queue governance/i)).toBeInTheDocument();
expect(await screen.findByText(/Quality and fallback signals/i)).toBeInTheDocument();
```

- [ ] **Step 2: Run targeted frontend test to verify failure**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\frontend
npm test -- --run src/App.test.tsx
```

Expected: FAIL because the dashboard does not yet present that narrative.

- [ ] **Step 3: Implement the dashboard narrative layer**

Update `frontend/src/App.tsx` to add:

- a concise architecture strip that names the multi-agent stages
- a queue/governance summary panel that explains scheduler, queue, worker, retry, and guard behavior
- a quality panel that explains trace completeness, tool success, fetch success, and fallback counts
- clearer run-detail copy that distinguishes compatibility snapshot fields from structured stage internals

Update `frontend/src/styles.css` so the new sections match the existing visual language and remain mobile-safe.

- [ ] **Step 4: Run frontend verification**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\frontend
npm test -- --run
npm run build
```

Expected: all tests pass and production build succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.tsx frontend/src/styles.css frontend/src/App.test.tsx
git commit -m "feat: strengthen dashboard showcase narrative"
```

### Task 4: Final Verification And Milestone Commit

**Files:**
- Modify: any remaining files touched by integration fixes

- [ ] **Step 1: Run backend verification**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest -q
```

Expected: all backend tests pass.

- [ ] **Step 2: Run frontend verification**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\frontend
npm test -- --run
npm run build
```

Expected: all frontend tests pass and build succeeds.

- [ ] **Step 3: Run repo hygiene checks**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp
git diff --check
git status --short
```

Expected: no whitespace errors and only intended showcase-alignment changes remain.

- [ ] **Step 4: Commit final milestone**

```bash
git add README.md backend/README.md PROJECT_TODO.md docs/resume-alignment.md backend frontend
git commit -m "feat: align project showcase with resume narrative"
```
