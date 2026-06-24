# MCP And Playwright Runtime Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing OneSearch MCP and Playwright MCP-compatible fallback boundaries into a truthful runtime-evidence slice with compact per-run summaries, visible degradation behavior, and matching API/UI proof surfaces.

**Architecture:** Keep the current provider adapters and fallback semantics, but derive a stable `integration_runtime` summary from configuration plus observed tool/fetch evidence. Expose that summary through the run snapshot and minimal HTML surfaces without changing the durable relational model or introducing new providers.

**Tech Stack:** Python 3.12, FastAPI backend, LangGraph run state, existing MCP/browser adapters, Jinja HTML pages, pytest

---

### Task 1: Add A Stable Runtime-Evidence Summary Helper

**Files:**
- Create: `backend/app/integrations/runtime_summary.py`
- Modify: `backend/app/core/config.py`
- Test: `backend/tests/test_tools_and_eval.py`

- [ ] **Step 1: Write the failing runtime-summary unit tests**

Add tests to `backend/tests/test_tools_and_eval.py` that assert:

```python
def test_build_integration_runtime_marks_onesearch_as_enabled_when_fully_configured() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
        mcp_gateway_provider="onesearch",
        onesearch_base_url="http://localhost:8090",
        browser_fetch_provider="playwright_mcp",
        playwright_mcp_base_url="http://localhost:8931",
        browser_allowed_domains=["example.com"],
    )

    runtime = build_integration_runtime(
        settings=settings,
        tool_results=[],
        fetched_contents=[],
    )

    assert runtime["mcp"] == {
        "configured_provider": "onesearch",
        "enabled": True,
        "selected_tool_path": "search_news",
        "base_url_configured": True,
        "used_in_run": False,
        "fallback_used": False,
        "fallback_provider": None,
        "fallback_reason": None,
        "tool_call_count": 0,
    }
    assert runtime["browser"]["configured_provider"] == "playwright_mcp"
    assert runtime["browser"]["enabled"] is True
    assert runtime["browser"]["allowed_domains"] == ["example.com"]


def test_build_integration_runtime_marks_browser_path_disabled_when_required_config_missing() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
        browser_fetch_provider="playwright_mcp",
        playwright_mcp_base_url="http://localhost:8931",
        browser_allowed_domains=[],
    )

    runtime = build_integration_runtime(
        settings=settings,
        tool_results=[],
        fetched_contents=[],
    )

    assert runtime["browser"]["configured_provider"] == "playwright_mcp"
    assert runtime["browser"]["enabled"] is False
    assert runtime["browser"]["used_in_run"] is False
    assert runtime["browser"]["allowed_domains"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.12 -m pytest backend/tests/test_tools_and_eval.py -q -k "integration_runtime"`

Expected: FAIL because no runtime-summary helper exists yet.

- [ ] **Step 3: Implement the runtime-summary helper**

Create `backend/app/integrations/runtime_summary.py`:

```python
from __future__ import annotations

from typing import Any

from app.core.config import Settings


def build_integration_runtime(
    *,
    settings: Settings | None,
    tool_results: list[dict[str, Any]],
    fetched_contents: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    mcp_provider = "local" if settings is None else settings.mcp_gateway_provider
    onesearch_enabled = bool(
        settings is not None
        and settings.mcp_gateway_provider == "onesearch"
        and settings.onesearch_base_url
    )

    mcp_tool_calls = [
        item
        for item in tool_results
        if str(item.get("tool_name")) == "search_news"
        and str(item.get("metadata", {}).get("provider")) == "onesearch_mcp"
    ]
    mcp_fallback = next(
        (
            item.get("metadata", {})
            for item in mcp_tool_calls
            if bool(item.get("metadata", {}).get("used_fallback"))
        ),
        None,
    )

    browser_provider = "none" if settings is None else settings.browser_fetch_provider
    browser_enabled = bool(
        settings is not None
        and settings.browser_fetch_provider == "playwright_mcp"
        and settings.playwright_mcp_base_url
        and settings.browser_allowed_domains
    )
    browser_fetched = [
        item for item in fetched_contents if item.get("fetch_method") == "browser_fallback"
    ]
    browser_failed = [
        item
        for item in fetched_contents
        if item.get("fetch_status") == "failed"
        and item.get("fetch_fallback_reason")
    ]

    return {
        "mcp": {
            "configured_provider": mcp_provider,
            "enabled": onesearch_enabled,
            "selected_tool_path": "search_news",
            "base_url_configured": bool(settings and settings.onesearch_base_url),
            "used_in_run": bool(mcp_tool_calls),
            "fallback_used": bool(mcp_fallback),
            "fallback_provider": None if mcp_fallback is None else mcp_fallback.get("fallback_provider"),
            "fallback_reason": None if mcp_fallback is None else mcp_fallback.get("fallback_reason"),
            "tool_call_count": len(mcp_tool_calls),
        },
        "browser": {
            "configured_provider": browser_provider,
            "enabled": browser_enabled,
            "selected_tool_path": "fetch_article_content.browser_fallback",
            "base_url_configured": bool(settings and settings.playwright_mcp_base_url),
            "allowed_domains": [] if settings is None else list(settings.browser_allowed_domains),
            "used_in_run": bool(browser_fetched),
            "fallback_used": bool(browser_fetched),
            "fallback_reason": None if not browser_fetched else browser_fetched[0].get("fetch_fallback_reason"),
            "browser_fetch_count": len(browser_fetched),
            "failed_browser_fetch_count": len(browser_failed),
        },
    }
```

No config-schema change is required in `backend/app/core/config.py`, but add a
small comment or keep imports stable only if needed.

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.12 -m pytest backend/tests/test_tools_and_eval.py -q -k "integration_runtime"`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/runtime_summary.py backend/tests/test_tools_and_eval.py
git commit -m "feat: add integration runtime summary helper"
```

### Task 2: Persist Runtime Evidence Into Monitor Run Snapshots

**Files:**
- Modify: `backend/app/agent/nodes.py`
- Modify: `backend/app/agent/graph.py`
- Modify: `backend/app/api/monitor.py`
- Test: `backend/tests/test_monitor_run_flow.py`

- [ ] **Step 1: Write the failing run-snapshot tests**

Add tests to `backend/tests/test_monitor_run_flow.py` that assert:

```python
def test_monitor_graph_attaches_integration_runtime_summary_for_onesearch_fallback() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
        mcp_gateway_provider="onesearch",
        onesearch_base_url="http://localhost:8090",
    )
    gateway = LocalToolGateway()
    gateway.register("rss_fetch", lambda run_id, topic: ToolResponse.success(
        tool_name="rss_fetch",
        summary="No RSS results.",
        data={"candidates": []},
    ))
    gateway.register("search_news", lambda run_id, topic: ToolResponse.success(
        tool_name="search_news",
        summary="onesearch_mcp failed; used mock_search fallback.",
        data={"run_id": run_id, "candidates": []},
        metadata={
            "provider": "onesearch_mcp",
            "fallback_provider": "mock_search",
            "used_fallback": True,
            "fallback_reason": "onesearch unavailable",
        },
    ))
    gateway.register("notification_send", lambda **kwargs: ToolResponse.success(
        tool_name="notification_send",
        summary="Notifications skipped.",
        data={"status": "skipped"},
    ))

    graph = build_monitor_graph(llm=MockLLM(), gateway=gateway, settings=settings)
    result = graph.invoke(_build_minimal_monitor_state())

    assert result["integration_runtime"]["mcp"]["enabled"] is True
    assert result["integration_runtime"]["mcp"]["used_in_run"] is True
    assert result["integration_runtime"]["mcp"]["fallback_used"] is True
    assert result["integration_runtime"]["mcp"]["fallback_provider"] == "mock_search"


def test_monitor_graph_attaches_browser_runtime_summary_from_fetched_contents() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
        browser_fetch_provider="playwright_mcp",
        playwright_mcp_base_url="http://localhost:8931",
        browser_allowed_domains=["example.com"],
    )
```

Then assert the final state contains:

```python
assert result["integration_runtime"]["browser"]["enabled"] is True
assert result["integration_runtime"]["browser"]["used_in_run"] is True
assert result["integration_runtime"]["browser"]["browser_fetch_count"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.12 -m pytest backend/tests/test_monitor_run_flow.py -q -k "integration_runtime_summary"`

Expected: FAIL because the graph does not yet derive or persist `integration_runtime`.

- [ ] **Step 3: Derive and attach runtime evidence during graph finalization**

Update `backend/app/agent/graph.py`:

```python
from app.integrations.runtime_summary import build_integration_runtime
```

and in `_run_supervisor_finalize_stage(...)` before calling
`supervisor_finalize_node(...)`:

```python
state["integration_runtime"] = build_integration_runtime(
    settings=settings,
    tool_results=list(state.get("tool_results", [])),
    fetched_contents=list(
        state.get("extraction_output", {}).get(
            "fetched_contents",
            state.get("fetched_contents", []),
        )
    ),
)
```

Update `backend/app/agent/nodes.py` so `supervisor_finalize_node(...)` mirrors
the derived section back into the compatibility snapshot:

```python
state["integration_runtime"] = dict(state.get("integration_runtime", {}))
```

Update any response-building logic in `backend/app/api/monitor.py` only if the
current code filters fields and would otherwise drop `integration_runtime`.

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.12 -m pytest backend/tests/test_monitor_run_flow.py -q -k "integration_runtime_summary"`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/graph.py backend/app/agent/nodes.py backend/app/api/monitor.py backend/tests/test_monitor_run_flow.py
git commit -m "feat: expose integration runtime in run snapshots"
```

### Task 3: Make Run Detail And Resume Pages Show The Runtime Evidence

**Files:**
- Modify: `backend/app/templates/run_detail.html`
- Modify: `backend/app/templates/resume_alignment.html`
- Test: `backend/tests/test_monitor_run_flow.py`

- [ ] **Step 1: Write the failing page/render tests**

Add or extend tests in `backend/tests/test_monitor_run_flow.py` to assert the
HTML responses include the new runtime evidence strings when the snapshot
contains `integration_runtime`, for example:

```python
def test_run_detail_page_renders_integration_runtime_summary(client: TestClient) -> None:
    response = client.get("/runs/run_001")

    assert response.status_code == 200
    assert "MCP runtime" in response.text
    assert "Browser fallback runtime" in response.text
```

If a template-only test setup already exists, assert on rendered text from the
template response instead.

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.12 -m pytest backend/tests/test_monitor_run_flow.py -q -k "run_detail_page_renders_integration_runtime_summary"`

Expected: FAIL because the page does not yet render the runtime summary.

- [ ] **Step 3: Update the HTML surfaces**

Update `backend/app/templates/run_detail.html` by adding a new section such as:

```html
<section class="section-card">
  <h3>MCP runtime</h3>
  <p>
    When configured, the monitor can route <code>search_news</code> through the
    OneSearch-compatible MCP boundary. This section shows whether that path was
    merely configured, actually used, or degraded to a fallback during the run.
  </p>
  <div class="grid two">
    <article class="stat">
      <strong>Configured provider</strong>
      <p id="mcp-provider">Visible in the run snapshot API.</p>
    </article>
    <article class="stat">
      <strong>Fallback strategy</strong>
      <p>Local search remains the explicit degradation path if the MCP provider fails.</p>
    </article>
  </div>
</section>

<section class="section-card">
  <h3>Browser fallback runtime</h3>
  <p>
    Browser fetch stays last in the retrieval chain: fixture or local content
    first, plain HTTP second, Playwright-compatible fallback only after failure.
  </p>
</section>
```

Keep the page explanatory, but truthful to the data boundary.

Update `backend/app/templates/resume_alignment.html` so the truth-boundary copy
shifts from pure boundary wording to runtime-evidence wording, for example:

```html
<li>Optional MCP and browser adapters now expose real per-run configuration, usage, and degradation evidence when live services are wired.</li>
<li>These remain optional runtime paths, not guaranteed always-live deployments.</li>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.12 -m pytest backend/tests/test_monitor_run_flow.py -q -k "run_detail_page_renders_integration_runtime_summary"`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/templates/run_detail.html backend/app/templates/resume_alignment.html backend/tests/test_monitor_run_flow.py
git commit -m "feat: surface mcp and browser runtime evidence in html"
```

### Task 4: Tighten README Truth And Run Full Verification

**Files:**
- Modify: `backend/README.md`
- Modify: `PROJECT_TODO.md`
- Test: `backend/tests/test_tools_and_eval.py`
- Test: `backend/tests/test_monitor_run_flow.py`
- Test: `backend/tests/test_topics_api.py`
- Test: `backend/tests/test_health_api.py`

- [ ] **Step 1: Add the final end-to-end assertions**

Extend a monitor-run test so it asserts:

```python
assert "integration_runtime" in result
assert "mcp" in result["integration_runtime"]
assert "browser" in result["integration_runtime"]
assert isinstance(result["integration_runtime"]["browser"]["allowed_domains"], list)
```

If the API readback path is covered, also assert:

```python
response = client.get(f"/api/monitor/runs/{run_id}")
assert "integration_runtime" in response.json()
```

- [ ] **Step 2: Update README wording to match the delivered slice**

Update `backend/README.md` so:

- the OneSearch path is described as a real optional runtime path with visible
  per-run evidence
- the Playwright path is described as a real optional governed fallback path
  with visible per-run evidence
- it still explicitly states these are not guaranteed live deployments in every
  environment

Example wording to add or revise:

```md
When configured, the run snapshot exposes an `integration_runtime` section that
shows whether the OneSearch-compatible MCP path or Playwright-compatible
browser fallback path was enabled, actually used, or degraded during the run.
This is runtime evidence, not a claim that all environments always wire live
external services.
```

- [ ] **Step 3: Run focused regression tests**

Run: `py -3.12 -m pytest backend/tests/test_tools_and_eval.py backend/tests/test_monitor_run_flow.py backend/tests/test_topics_api.py backend/tests/test_health_api.py -q`

Expected: PASS

- [ ] **Step 4: Run full backend suite and hygiene checks**

Run: `py -3.12 -m pytest backend -q`

Expected: PASS

Run: `git diff --check`

Expected: no output

- [ ] **Step 5: Update milestone tracking and commit**

Update `PROJECT_TODO.md` to add the completed milestone:

- `implement mcp and playwright runtime evidence slice`
- `spec and planning for mcp and playwright runtime evidence`

Then commit:

```bash
git add backend/README.md PROJECT_TODO.md backend/tests/test_tools_and_eval.py backend/tests/test_monitor_run_flow.py
git commit -m "feat: complete mcp and playwright runtime evidence slice"
```

## Self-Review

### Spec coverage

- runtime summary contract is implemented in Task 1
- run snapshot integration is implemented in Task 2
- HTML/runtime evidence visibility is implemented in Task 3
- README truth and final verification are implemented in Task 4

### Placeholder scan

- No `TBD`, `TODO`, or deferred placeholders remain in the tasks
- Every task includes exact file paths and exact commands

### Type consistency

- One stable runtime field name is used throughout: `integration_runtime`
- Summary sections remain consistently named `mcp` and `browser`
- The plan keeps the existing provider names: `onesearch`, `onesearch_mcp`,
  and `playwright_mcp`
