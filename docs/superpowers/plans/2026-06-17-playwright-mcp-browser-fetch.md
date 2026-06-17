# Playwright MCP Browser Fetch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional Playwright MCP-compatible browser fetch provider behind the existing `BrowserFetchTool` fallback path.

**Architecture:** Keep Agent nodes provider-agnostic: they continue to call `fetch_article_content` through the gateway. `BrowserFetchTool` still attempts fixture/HTTP fetch first, then calls a configured browser fallback only when primary fetch fails. The new provider is a small HTTP client adapter with domain allow-list, timeout, synchronous concurrency limit, and content-length controls.

**Tech Stack:** FastAPI backend, Pydantic settings, httpx-compatible client injection, pytest, existing `LocalToolGateway`.

---

## Guidance Boundaries

- Do not add free browsing by the Agent.
- Do not make Playwright MCP the default fetch path.
- Do not claim a production browser service; this is an optional provider integration path.
- Do not hide fallback failures. Preserve `fetch_status`, `fetch_error`, `fetch_fallback_reason`, and metadata.
- Keep mocks deterministic for tests.

## File Structure

- Modify `backend/app/core/config.py`: add browser provider settings.
- Modify `backend/app/tools/browser_fetch_tool.py`: add Playwright MCP-compatible client and controlled fallback metadata.
- Modify `backend/app/tools/registry.py`: wire the optional browser fallback provider via settings.
- Modify `backend/tests/test_tools_and_eval.py`: add focused TDD tests.
- Modify `backend/README.md`: truthfully move only the optional provider path into implemented capabilities.

## Task 1: Settings Contract

**Files:**
- Modify: `backend/app/core/config.py`
- Test: `backend/tests/test_tools_and_eval.py`

- [ ] **Step 1: Write the failing test**

```python
def test_settings_accept_browser_fetch_provider_values() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
        browser_fetch_provider="playwright_mcp",
        playwright_mcp_base_url="http://localhost:8931",
        playwright_mcp_timeout_seconds=4.0,
        browser_allowed_domains=["example.com", "news.example.com"],
        browser_max_concurrency=1,
        browser_max_content_chars=2048,
    )

    assert settings.browser_fetch_provider == "playwright_mcp"
    assert settings.playwright_mcp_base_url == "http://localhost:8931"
    assert settings.playwright_mcp_timeout_seconds == 4.0
    assert settings.browser_allowed_domains == ["example.com", "news.example.com"]
    assert settings.browser_max_concurrency == 1
    assert settings.browser_max_content_chars == 2048
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.12 -m pytest tests/test_tools_and_eval.py::test_settings_accept_browser_fetch_provider_values -q`

Expected: FAIL because browser settings do not exist yet.

- [ ] **Step 3: Write minimal implementation**

Add fields to `Settings`:

The current browser fallback path is synchronous, so `browser_max_concurrency`
is an explicit limit of `1`; a browser worker pool is out of scope for this
slice.

```python
browser_fetch_provider: str = Field(default="none")
playwright_mcp_base_url: str | None = Field(default=None)
playwright_mcp_timeout_seconds: float = Field(default=10.0)
browser_allowed_domains: list[str] = Field(default_factory=list)
browser_max_concurrency: int = Field(default=1)
browser_max_content_chars: int = Field(default=20000)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.12 -m pytest tests/test_tools_and_eval.py::test_settings_accept_browser_fetch_provider_values -q`

Expected: PASS.

## Task 2: Controlled Playwright MCP Client

**Files:**
- Modify: `backend/app/tools/browser_fetch_tool.py`
- Test: `backend/tests/test_tools_and_eval.py`

- [ ] **Step 1: Write failing tests**

```python
def test_playwright_mcp_browser_fetcher_calls_allowed_domain_and_truncates() -> None:
    from app.tools.browser_fetch_tool import PlaywrightMCPBrowserFetcher

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"content": "abcdef"}

    class FakeClient:
        def __init__(self) -> None:
            self.requests: list[dict[str, object]] = []

        def post(self, url: str, **kwargs: object) -> FakeResponse:
            self.requests.append({"url": url, **kwargs})
            return FakeResponse()

    client = FakeClient()
    fetcher = PlaywrightMCPBrowserFetcher(
        base_url="http://localhost:8931",
        allowed_domains=["example.com"],
        http_client=client,
        timeout_seconds=3.0,
        max_content_chars=4,
    )

    content = fetcher("https://example.com/articles/dynamic")

    assert content == "abcd"
    assert client.requests[0]["url"] == "http://localhost:8931/fetch"
    assert client.requests[0]["json"] == {"url": "https://example.com/articles/dynamic"}
    assert client.requests[0]["timeout"] == 3.0


def test_playwright_mcp_browser_fetcher_rejects_disallowed_domain() -> None:
    from app.tools.browser_fetch_tool import PlaywrightMCPBrowserFetcher

    fetcher = PlaywrightMCPBrowserFetcher(
        base_url="http://localhost:8931",
        allowed_domains=["example.com"],
    )

    with pytest.raises(ValueError, match="not allowed"):
        fetcher("https://evil.example.net/story")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.12 -m pytest tests/test_tools_and_eval.py::test_playwright_mcp_browser_fetcher_calls_allowed_domain_and_truncates tests/test_tools_and_eval.py::test_playwright_mcp_browser_fetcher_rejects_disallowed_domain -q`

Expected: FAIL because `PlaywrightMCPBrowserFetcher` does not exist.

- [ ] **Step 3: Write minimal implementation**

Implement `PlaywrightMCPBrowserFetcher` in `browser_fetch_tool.py` with:

- normalized `base_url`
- `allowed_domains` exact host or subdomain matching
- injected `http_client` or `httpx`
- `POST {base_url}/fetch` with `{"url": url}`
- JSON response parsing from `content`, `text`, or `markdown`
- concurrency limit through `max_concurrency`
- content truncation to `max_content_chars`

- [ ] **Step 4: Run tests to verify they pass**

Run the same focused tests.

Expected: PASS.

## Task 3: Registry Wiring And Fallback Metadata

**Files:**
- Modify: `backend/app/tools/registry.py`
- Test: `backend/tests/test_tools_and_eval.py`

- [ ] **Step 1: Write failing test**

```python
def test_build_default_tool_registry_wires_playwright_mcp_browser_fallback() -> None:
    from app.core.config import Settings
    from app.tools.registry import build_default_tool_registry

    class FakeBrowserResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"content": "dynamic browser content"}

    class FakeBrowserClient:
        def __init__(self) -> None:
            self.requests: list[dict[str, object]] = []

        def post(self, url: str, **kwargs: object) -> FakeBrowserResponse:
            self.requests.append({"url": url, **kwargs})
            return FakeBrowserResponse()

    class FailingHTTPClient:
        def get(self, url: str, **kwargs: object) -> object:
            raise RuntimeError("plain http failed")

    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
        browser_fetch_provider="playwright_mcp",
        playwright_mcp_base_url="http://localhost:8931",
        browser_allowed_domains=["example.com"],
    )
    browser_client = FakeBrowserClient()
    registry = build_default_tool_registry(
        llm=MockLLM(),
        settings=settings,
        fetch_http_client=FailingHTTPClient(),
        browser_http_client=browser_client,
    )
    gateway = LocalToolGateway()
    registry.register_into(gateway)

    response = gateway.call(
        "fetch_article_content",
        candidates=[
            {
                "candidate_id": "cand_dynamic",
                "url": "https://example.com/articles/dynamic",
                "raw_summary": "Dynamic summary",
            }
        ],
    )

    assert response.success is True
    assert response.data is not None
    candidate = response.data["candidates"][0]
    assert candidate["fetch_status"] == "fetched"
    assert candidate["fetch_method"] == "browser_fallback"
    assert candidate["content"] == "dynamic browser content"
    assert response.metadata["used_browser_fallback"] is True
    assert response.metadata["browser_provider"] == "playwright_mcp"
    assert browser_client.requests[0]["url"] == "http://localhost:8931/fetch"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.12 -m pytest tests/test_tools_and_eval.py::test_build_default_tool_registry_wires_playwright_mcp_browser_fallback -q`

Expected: FAIL because registry does not accept browser clients or settings yet.

- [ ] **Step 3: Write minimal implementation**

Update `BrowserFetchTool` to accept a `browser_provider` metadata label. Update `build_default_tool_registry` to accept `fetch_http_client` and `browser_http_client`, then build `PlaywrightMCPBrowserFetcher` only when:

- `settings.browser_fetch_provider == "playwright_mcp"`
- `settings.playwright_mcp_base_url` is set
- `settings.browser_allowed_domains` is non-empty

- [ ] **Step 4: Run test to verify it passes**

Run the focused test.

Expected: PASS.

## Task 4: Documentation And Full Verification

**Files:**
- Modify: `backend/README.md`

- [ ] **Step 1: Update README**

State implemented:

- Optional Playwright MCP-compatible browser fetch provider behind `fetch_article_content`
- Provider is only used as HTTP fallback
- Domain allow-list, timeout, and content-length cap are required controls

Keep not claimed:

- General autonomous browsing
- Production browser fleet hardening
- Elasticsearch/OpenSearch external index
- Real embedding service/vector database

- [ ] **Step 2: Run verification**

From `backend`:

```powershell
py -3.12 -m pytest -q
py -3.12 -m compileall app
```

From repo root:

```powershell
git diff --check
docker compose config --quiet
git status --short --branch
```

- [ ] **Step 3: Commit and push**

```powershell
git add docs/superpowers/plans/2026-06-17-playwright-mcp-browser-fetch.md backend/app/core/config.py backend/app/tools/browser_fetch_tool.py backend/app/tools/registry.py backend/tests/test_tools_and_eval.py backend/README.md
git commit -m "feat: add playwright mcp browser fallback"
git push
```
