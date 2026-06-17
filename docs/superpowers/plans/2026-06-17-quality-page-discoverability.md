# Quality Page Discoverability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the already implemented quality summary page discoverable and keep README delivery documentation aligned with current routes.

**Architecture:** This is a presentation and documentation consistency slice. The `/quality` page and `/api/eval/summary` endpoint already exist; this change only exposes the page in shared HTML navigation and documents the existing API/page in README.

**Tech Stack:** FastAPI Jinja templates, pytest, Markdown.

---

### Task 1: Expose Quality Page In Admin Navigation

**Files:**
- Modify: `backend/app/templates/base.html`
- Test: `backend/tests/test_topics_api.py`

- [ ] **Step 1: Write the failing test**

Update `test_topics_html_page_renders` so the root admin page must expose the quality summary link:

```python
assert 'href="/quality"' in response.text
assert "质量汇总" in response.text
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_topics_api.py::test_topics_html_page_renders -q
```

Expected: FAIL because the shared nav does not link to `/quality`.

- [ ] **Step 3: Write minimal implementation**

Add one link to the shared navigation in `backend/app/templates/base.html`:

```html
<a href="/quality">质量汇总</a>
```

- [ ] **Step 4: Run focused tests**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest tests/test_topics_api.py -q
```

Expected: PASS.

### Task 2: Align README Route Inventory

**Files:**
- Modify: `backend/README.md`

- [ ] **Step 1: Document existing eval summary API**

Add `GET /api/eval/summary` to the MVP APIs list because the route exists and is tested.

- [ ] **Step 2: Document existing quality HTML page**

Add `GET /quality` to the Minimal HTML Pages list because the route exists and is tested.

- [ ] **Step 3: Run verification**

Run:

```powershell
cd E:\bgagent2\.worktrees\feat-industry-news-mvp\backend
py -3.12 -m pytest -q
py -3.12 -m compileall app
cd E:\bgagent2\.worktrees\feat-industry-news-mvp
docker compose config --quiet
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 4: Commit and push**

Run:

```powershell
git add docs/superpowers/plans/2026-06-17-quality-page-discoverability.md backend/app/templates/base.html backend/tests/test_topics_api.py backend/README.md
git commit -m "docs: expose quality summary page"
git push
```
