# OneSearch MCP Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional OneSearch-compatible MCP gateway boundary for candidate retrieval while preserving deterministic local defaults and visible fallback behavior.

**Architecture:** Keep Agent nodes provider-agnostic. A new `OneSearchMCPGateway` will implement the existing `ToolGateway` interface, handle only `search_news`, and delegate all other tools to a local fallback gateway. The graph build path becomes provider-aware through settings, and provider failure must degrade to deterministic local search with explicit metadata and event evidence.

**Tech Stack:** FastAPI backend, Pydantic settings, `ToolGateway` abstraction, httpx-compatible client injection, pytest, existing `LocalToolGateway`.

---

## Guidance Boundaries

- Do not add raw MCP session management in this slice.
- Do not make OneSearch the default path.
- Do not remove `mock_search` or `LocalToolGateway`.
- Do not move `fetch_article_content`, extraction, dedup, scoring, push decision, or notification into the OneSearch provider path.
- Do not hide provider failures. Preserve provider, fallback provider, and fallback reason in `ToolResponse` metadata and run events.
- Do not claim a verified live OneSearch MCP deployment in code or docs.

## File Structure

- Modify `backend/app/core/config.py`: add explicit MCP gateway and OneSearch settings.
- Modify `backend/app/mcp/gateway.py`: add a small gateway builder contract or helper types if needed.
- Create `backend/app/mcp/onesearch_gateway.py`: add OneSearch-compatible HTTP wrapper adapter implementing `ToolGateway`.
- Modify `backend/app/agent/graph.py`: build the provider-aware gateway without pushing provider branching into nodes.
- Modify `backend/tests/test_tools_and_eval.py`: add configuration and gateway-focused TDD coverage.
- Modify `backend/tests/test_monitor_run_flow.py`: add monitor-flow evidence for provider fallback visibility.
- Modify `backend/README.md`: document the narrow, truthful capability boundary.

## Task 1: Freeze The Settings Contract

**Files:**
- Modify: `backend/app/core/config.py`
- Test: `backend/tests/test_tools_and_eval.py`

- [ ] **Step 1: Write the failing test**

Add this test near the other provider-setting tests:

```python
def test_settings_accept_onesearch_gateway_provider_values() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
        mcp_gateway_provider="onesearch",
        onesearch_base_url="http://localhost:8090",
        onesearch_timeout_seconds=4.5,
        onesearch_max_results=7,
    )

    assert settings.mcp_gateway_provider == "onesearch"
    assert settings.onesearch_base_url == "http://localhost:8090"
    assert settings.onesearch_timeout_seconds == 4.5
    assert settings.onesearch_max_results == 7
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
cd backend
py -3.12 -m pytest tests/test_tools_and_eval.py::test_settings_accept_onesearch_gateway_provider_values -q
```

Expected: FAIL because the settings fields do not exist yet.

- [ ] **Step 3: Write minimal implementation**

Add these fields to `Settings` in `backend/app/core/config.py`:

```python
mcp_gateway_provider: str = Field(default="local")
onesearch_base_url: str | None = Field(default=None)
onesearch_timeout_seconds: float = Field(default=10.0, gt=0.0)
onesearch_max_results: int = Field(default=10, gt=0)
```

Keep the existing search provider settings unchanged. This slice adds a gateway-level choice, not a replacement for `search_provider`.

- [ ] **Step 4: Run test to verify it passes**

Run the same focused command.

Expected: PASS.

## Task 2: Add A Dedicated OneSearch Gateway Adapter

**Files:**
- Create: `backend/app/mcp/onesearch_gateway.py`
- Test: `backend/tests/test_tools_and_eval.py`

- [ ] **Step 1: Write the failing tests**

Add these tests:

```python
def test_onesearch_gateway_calls_wrapper_and_maps_results() -> None:
    from app.mcp.local_gateway import LocalToolGateway
    from app.mcp.onesearch_gateway import OneSearchMCPGateway
    from app.tools.responses import ToolResponse

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "results": [
                    {
                        "title": "OpenAI ships enterprise agent workflow",
                        "url": "https://example.com/agent-workflow",
                        "snippet": "Enterprise workflow update.",
                        "source": "example.com",
                        "published_at": "2026-06-17T10:00:00Z",
                    }
                ]
            }

    class FakeHttpClient:
        def __init__(self) -> None:
            self.requests: list[dict[str, object]] = []

        def post(self, url: str, **kwargs: object) -> FakeResponse:
            self.requests.append({"url": url, **kwargs})
            return FakeResponse()

    fallback_gateway = LocalToolGateway()
    fallback_gateway.register(
        "fetch_article_content",
        lambda **kwargs: ToolResponse.success(
            tool_name="fetch_article_content",
            summary="local fetch",
            data={"candidates": []},
        ),
    )
    gateway = OneSearchMCPGateway(
        base_url="http://localhost:8090",
        http_client=FakeHttpClient(),
        fallback_gateway=fallback_gateway,
        timeout_seconds=4.0,
        max_results=5,
    )

    response = gateway.call(
        "search_news",
        run_id="run_onesearch_001",
        topic={
            "topic_id": "topic_ai_agent",
            "name": "AI Agent",
            "seed_keywords": ["OpenAI", "enterprise"],
        },
    )

    assert response.success is True
    assert response.data is not None
    assert response.data["candidates"][0]["source_name"] == "example.com"
    assert response.metadata["provider"] == "onesearch_mcp"
    assert response.metadata["used_fallback"] is False
```

```python
def test_onesearch_gateway_falls_back_to_local_mock_search_when_provider_fails() -> None:
    from app.mcp.local_gateway import LocalToolGateway
    from app.mcp.onesearch_gateway import OneSearchMCPGateway
    from app.tools.responses import ToolResponse

    class FailingHttpClient:
        def post(self, url: str, **kwargs: object) -> object:
            raise RuntimeError("onesearch unavailable")

    fallback_gateway = LocalToolGateway()
    fallback_gateway.register(
        "search_news",
        lambda run_id, topic: ToolResponse.success(
            tool_name="search_news",
            summary="Used local mock search fallback.",
            data={
                "run_id": run_id,
                "candidates": [
                    {
                        "candidate_id": "cand_local_001",
                        "run_id": run_id,
                        "topic_id": topic["topic_id"],
                        "source_type": "search",
                        "source_name": "AI Search",
                        "title": "Fallback item",
                        "url": "https://example.com/fallback",
                        "published_at": None,
                        "raw_summary": "Fallback summary",
                        "fetch_status": "pending",
                    }
                ],
            },
            metadata={
                "provider": "mock_search",
                "used_fallback": False,
            },
        ),
    )
    gateway = OneSearchMCPGateway(
        base_url="http://localhost:8090",
        http_client=FailingHttpClient(),
        fallback_gateway=fallback_gateway,
        timeout_seconds=4.0,
        max_results=5,
    )

    response = gateway.call(
        "search_news",
        run_id="run_onesearch_fallback",
        topic={
            "topic_id": "topic_ai_agent",
            "name": "AI Agent",
            "seed_keywords": ["OpenAI", "enterprise"],
        },
    )

    assert response.success is True
    assert response.metadata["provider"] == "onesearch_mcp"
    assert response.metadata["fallback_provider"] == "mock_search"
    assert response.metadata["used_fallback"] is True
    assert response.metadata["fallback_reason"] == "onesearch unavailable"
    assert response.data is not None
    assert response.data["candidates"][0]["title"] == "Fallback item"
```

```python
def test_onesearch_gateway_delegates_non_search_tools_to_fallback_gateway() -> None:
    from app.mcp.local_gateway import LocalToolGateway
    from app.mcp.onesearch_gateway import OneSearchMCPGateway
    from app.tools.responses import ToolResponse

    fallback_gateway = LocalToolGateway()
    fallback_gateway.register(
        "fetch_article_content",
        lambda **kwargs: ToolResponse.success(
            tool_name="fetch_article_content",
            summary="delegated",
            data={"candidates": [{"candidate_id": "cand_001"}]},
            metadata={"provider": "local_gateway"},
        ),
    )
    gateway = OneSearchMCPGateway(
        base_url="http://localhost:8090",
        fallback_gateway=fallback_gateway,
    )

    response = gateway.call(
        "fetch_article_content",
        candidates=[{"candidate_id": "cand_001"}],
    )

    assert response.success is True
    assert response.summary == "delegated"
    assert response.data == {"candidates": [{"candidate_id": "cand_001"}]}
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
cd backend
py -3.12 -m pytest tests/test_tools_and_eval.py::test_onesearch_gateway_calls_wrapper_and_maps_results tests/test_tools_and_eval.py::test_onesearch_gateway_falls_back_to_local_mock_search_when_provider_fails tests/test_tools_and_eval.py::test_onesearch_gateway_delegates_non_search_tools_to_fallback_gateway -q
```

Expected: FAIL because `OneSearchMCPGateway` does not exist.

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/mcp/onesearch_gateway.py` with a focused adapter:

```python
from __future__ import annotations

from typing import Any
import uuid

from app.mcp.gateway import ToolCallable, ToolGateway
from app.tools.responses import ToolResponse

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None


class OneSearchMCPGateway(ToolGateway):
    def __init__(
        self,
        *,
        base_url: str,
        fallback_gateway: ToolGateway,
        http_client: Any | None = None,
        timeout_seconds: float = 10.0,
        max_results: int = 10,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.fallback_gateway = fallback_gateway
        self.http_client = http_client
        self.timeout_seconds = timeout_seconds
        self.max_results = max_results
        self._handlers: dict[str, ToolCallable] = {}

    def register(self, tool_name: str, handler: ToolCallable) -> None:
        self._handlers[tool_name] = handler

    def _get_http_client(self) -> Any:
        if self.http_client is not None:
            return self.http_client
        if httpx is None:
            raise RuntimeError("httpx is unavailable for OneSearch requests.")
        return httpx

    def _build_query(self, topic: dict[str, Any]) -> tuple[str, list[str]]:
        query_terms = [str(topic.get("name", "")), *topic.get("seed_keywords", [])]
        query = " ".join(term for term in query_terms if term).strip()
        return query, query_terms

    def _map_result(
        self,
        *,
        run_id: str,
        topic_id: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        url = str(result.get("url") or "").strip()
        title = str(result.get("title") or url).strip()
        snippet = str(result.get("snippet") or result.get("content") or "").strip()
        source_name = str(result.get("source") or "OneSearch")
        candidate_key = f"{url}|{title}"
        return {
            "candidate_id": f"cand_search_{uuid.uuid5(uuid.NAMESPACE_URL, candidate_key).hex[:12]}",
            "run_id": run_id,
            "topic_id": topic_id,
            "source_type": "search",
            "source_name": source_name,
            "title": title,
            "url": url,
            "published_at": result.get("published_at"),
            "raw_summary": snippet,
            "fetch_status": "pending",
        }

    def _search_news(self, *, run_id: str, topic: dict[str, Any]) -> ToolResponse:
        topic_id = str(topic["topic_id"])
        query, query_terms = self._build_query(topic)
        try:
            response = self._get_http_client().post(
                f"{self.base_url}/search",
                json={"query": query, "max_results": self.max_results},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            raw_results = payload.get("results", []) if isinstance(payload, dict) else []
            candidates = [
                self._map_result(run_id=run_id, topic_id=topic_id, result=dict(item))
                for item in raw_results
                if isinstance(item, dict) and str(item.get("url") or "").strip()
            ]
            return ToolResponse.success(
                tool_name="search_news",
                summary=f"Loaded {len(candidates)} search candidate(s) from OneSearch.",
                data={"run_id": run_id, "candidates": candidates},
                metadata={
                    "provider": "onesearch_mcp",
                    "query": query,
                    "query_terms": query_terms,
                    "used_fallback": False,
                },
            )
        except Exception as exc:
            fallback_response = self.fallback_gateway.call(
                "search_news",
                run_id=run_id,
                topic=topic,
            )
            return ToolResponse(
                success=fallback_response.success,
                tool_name="search_news",
                summary="onesearch_mcp failed; used mock_search fallback.",
                data=fallback_response.data,
                error=fallback_response.error,
                metadata={
                    **dict(fallback_response.metadata),
                    "provider": "onesearch_mcp",
                    "fallback_provider": "mock_search",
                    "used_fallback": True,
                    "fallback_reason": str(exc),
                },
            )

    def call(self, tool_name: str, **kwargs: object) -> ToolResponse:
        if tool_name == "search_news":
            return self._search_news(
                run_id=str(kwargs["run_id"]),
                topic=dict(kwargs["topic"]),
            )
        return self.fallback_gateway.call(tool_name, **kwargs)
```

Do not add support for any tool other than `search_news`.

- [ ] **Step 4: Run tests to verify they pass**

Run the same focused command.

Expected: PASS.

## Task 3: Build The Provider-Aware Gateway Without Changing Node Semantics

**Files:**
- Modify: `backend/app/agent/graph.py`
- Modify: `backend/app/tools/registry.py`
- Test: `backend/tests/test_tools_and_eval.py`

- [ ] **Step 1: Write the failing tests**

Add these tests:

```python
def test_build_monitor_graph_uses_local_gateway_by_default() -> None:
    from app.agent.graph import _build_default_gateway
    from app.mcp.local_gateway import LocalToolGateway

    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
    )

    gateway = _build_default_gateway(MockLLM(), settings)

    assert isinstance(gateway, LocalToolGateway)
```

```python
def test_build_monitor_graph_uses_onesearch_gateway_when_configured() -> None:
    from app.agent.graph import _build_default_gateway
    from app.mcp.onesearch_gateway import OneSearchMCPGateway

    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
        mcp_gateway_provider="onesearch",
        onesearch_base_url="http://localhost:8090",
    )

    gateway = _build_default_gateway(MockLLM(), settings)

    assert isinstance(gateway, OneSearchMCPGateway)
```

```python
def test_build_monitor_graph_degrades_to_local_gateway_when_onesearch_config_is_incomplete() -> None:
    from app.agent.graph import _build_default_gateway
    from app.mcp.local_gateway import LocalToolGateway

    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
        mcp_gateway_provider="onesearch",
        onesearch_base_url=None,
    )

    gateway = _build_default_gateway(MockLLM(), settings)

    assert isinstance(gateway, LocalToolGateway)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
cd backend
py -3.12 -m pytest tests/test_tools_and_eval.py::test_build_monitor_graph_uses_local_gateway_by_default tests/test_tools_and_eval.py::test_build_monitor_graph_uses_onesearch_gateway_when_configured tests/test_tools_and_eval.py::test_build_monitor_graph_degrades_to_local_gateway_when_onesearch_config_is_incomplete -q
```

Expected: FAIL because gateway building is still always local and not provider-aware.

- [ ] **Step 3: Write minimal implementation**

Update `build_default_tool_registry()` so it always registers:

- `rss_fetch`
- `mock_search`
- `search_news`
- `fetch_article_content`
- `extract_article`
- `deduplicate_items`
- `score_candidate`
- `decide_push`
- `notification_send`

Make `search_news` deterministic by default:

```python
registry.register("search_news", SearchCandidatesTool())
```

Do not remove the existing optional `open_websearch` tool builder. Keep it available for the local gateway path by changing the search tool selection logic to:

```python
search_tool: ToolHandler = SearchCandidatesTool()
if settings is not None:
    provider_tool = _build_search_provider_tool(
        settings=settings,
        search_http_client=search_http_client,
    )
    if provider_tool is not None:
        search_tool = provider_tool
registry.register("search_news", search_tool)
```

Then update `backend/app/agent/graph.py` so `_build_default_gateway()`:

1. builds a `LocalToolGateway`
2. registers the default tool registry into that local gateway
3. returns the local gateway unless:
   - `settings is not None`
   - `settings.mcp_gateway_provider == "onesearch"`
   - `settings.onesearch_base_url` is truthy
4. otherwise returns:

```python
OneSearchMCPGateway(
    base_url=settings.onesearch_base_url,
    fallback_gateway=local_gateway,
    timeout_seconds=settings.onesearch_timeout_seconds,
    max_results=settings.onesearch_max_results,
)
```

Keep the function return type widened from `LocalToolGateway` to `ToolGateway`.

- [ ] **Step 4: Run tests to verify they pass**

Run the same focused command.

Expected: PASS.

## Task 4: Preserve Fallback Visibility In Monitor Runs

**Files:**
- Modify: `backend/tests/test_monitor_run_flow.py`
- Modify: `backend/app/agent/nodes.py` only if current event payloads are insufficient

- [ ] **Step 1: Write the failing test**

Add a monitor-flow test that exercises OneSearch fallback through the existing event path:

```python
def test_monitor_graph_records_onesearch_provider_fallback_event() -> None:
    class RecordingMonitorRunRepository:
        def __init__(self) -> None:
            self.monitor_runs: list[object] = []
            self.run_events: list[dict[str, object]] = []
            self.eval_results: list[dict[str, object]] = []

        def upsert_monitor_run(self, payload: object) -> object:
            self.monitor_runs.append(payload)
            return payload

        def list_push_history(self, topic_id: str) -> list[dict[str, object]]:
            return []

        def create_push_records(self, payloads: tuple[object, ...]) -> list[dict[str, object]]:
            return []

        def upsert_candidate_records(self, payloads: tuple[object, ...]) -> list[dict[str, object]]:
            return []

        def list_candidate_records(self, run_id: str) -> list[dict[str, object]]:
            return []

        def upsert_extracted_item_records(self, payloads: tuple[object, ...]) -> list[dict[str, object]]:
            return []

        def list_extracted_item_records(self, run_id: str) -> list[dict[str, object]]:
            return []

        def upsert_decision_records(self, payloads: tuple[object, ...]) -> list[dict[str, object]]:
            return []

        def list_decision_records(self, run_id: str) -> list[dict[str, object]]:
            return []

        def create_run_events(self, payloads: tuple[object, ...]) -> list[dict[str, object]]:
            persisted = [
                {
                    "run_id": payload.run_id,
                    "topic_id": payload.topic_id,
                    "event_type": payload.event_type,
                    "node": payload.node,
                    "message": payload.message,
                    "payload": payload.payload,
                    "elapsed_ms": payload.elapsed_ms,
                }
                for payload in payloads
            ]
            self.run_events.extend(persisted)
            return persisted

        def create_eval_result(self, payload: object) -> dict[str, object]:
            persisted = {
                "eval_id": "eval_001",
                "run_id": payload.run_id,
                "topic_id": payload.topic_id,
                "retrieved_count": payload.retrieved_count,
                "deduped_count": payload.deduped_count,
                "dedup_rate": payload.dedup_rate,
                "push_count": payload.push_count,
                "duplicate_push_count": payload.duplicate_push_count,
                "tool_success_rate": payload.tool_success_rate,
                "fetch_success_rate": payload.fetch_success_rate,
                "trace_completeness": payload.trace_completeness,
                "raw_summary_count": payload.raw_summary_count,
                "browser_fallback_count": payload.browser_fallback_count,
                "provider_fallback_count": payload.provider_fallback_count,
                "judge_mode": payload.judge_mode,
                "judge_score": payload.judge_score,
                "judge_reason": payload.judge_reason,
                "judge_issues": list(payload.judge_issues),
                "suggestions": list(payload.suggestions),
            }
            self.eval_results.append(persisted)
            return persisted

    repository = RecordingMonitorRunRepository()

    def search_news_tool(run_id: str, topic: dict[str, object]) -> ToolResponse:
        return ToolResponse.success(
            tool_name="search_news",
            summary="onesearch_mcp failed; used mock_search fallback.",
            data={"run_id": run_id, "candidates": []},
            metadata={
                "provider": "onesearch_mcp",
                "fallback_provider": "mock_search",
                "used_fallback": True,
                "fallback_reason": "onesearch unavailable",
            },
        )

    gateway = LocalToolGateway()
    gateway.register("rss_fetch", lambda run_id, topic: ToolResponse.success(
        tool_name="rss_fetch",
        summary="No RSS candidates.",
        data={"run_id": run_id, "candidates": []},
    ))
    gateway.register("search_news", search_news_tool)
    gateway.register("fetch_article_content", lambda candidates: ToolResponse.success(
        tool_name="fetch_article_content",
        summary="No fetched contents.",
        data={"candidates": []},
    ))
    gateway.register("extract_article", lambda run_id, topic, candidates: ToolResponse.success(
        tool_name="extract_article",
        summary="No extracted items.",
        data={"articles": [], "skipped_candidate_ids": []},
    ))
    gateway.register("deduplicate_items", lambda articles: ToolResponse.success(
        tool_name="deduplicate_items",
        summary="No deduped items.",
        data={"articles": [], "deduped_count": 0, "dropped_candidate_ids": []},
    ))
    gateway.register("score_candidate", lambda topic, articles: ToolResponse.success(
        tool_name="score_candidate",
        summary="No scored items.",
        data={"articles": []},
    ))
    gateway.register("decide_push", lambda run_id, topic, articles, push_history: ToolResponse.success(
        tool_name="decide_push",
        summary="No push decisions.",
        data={"pushes": [], "push_count": 0},
    ))

    graph = build_monitor_graph(
        llm=MockLLM(),
        gateway=gateway,
        run_repository=repository,
    )

    result = graph.invoke(
        {
            "run_id": "run_onesearch_event",
            "topic_id": "topic_ai_agent",
            "topic": {
                "topic_id": "topic_ai_agent",
                "name": "AI Agent",
                "description": "Track enterprise AI agent launches.",
                "seed_keywords": ["OpenAI", "enterprise"],
                "trusted_sources": ["AI Search"],
                "exclude_keywords": [],
                "push_threshold": 0.72,
                "cooldown_hours": 24,
                "enabled": True,
            },
            "seed_keywords": ["OpenAI", "enterprise"],
            "expanded_queries": [],
            "business_context": {},
            "source_plan": ["search_news"],
            "candidate_items": [],
            "fetched_contents": [],
            "extracted_items": [],
            "deduped_items": [],
            "scored_items": [],
            "final_decisions": [],
            "decision_reasons": [],
            "push_records": [],
            "push_history": [],
            "tool_results": [],
            "eval_result": {},
            "events": [],
            "errors": [],
            "status": "created",
        }
    )

    fallback_event = next(
        event for event in result["events"] if event["event_type"] == "fallback_used"
    )
    assert fallback_event["payload"]["provider"] == "onesearch_mcp"
    assert fallback_event["payload"]["fallback_provider"] == "mock_search"
    assert fallback_event["payload"]["fallback_reason"] == "onesearch unavailable"
    assert result["eval_result"]["provider_fallback_count"] == 1
```

- [ ] **Step 2: Run test to verify it fails only if event visibility is missing**

Run:

```powershell
cd backend
py -3.12 -m pytest tests/test_monitor_run_flow.py::test_monitor_graph_records_onesearch_provider_fallback_event -q
```

Expected: PASS if current node behavior already preserves the required metadata. FAIL only if event payloads or eval counts are not aligned.

- [ ] **Step 3: Write minimal implementation only if needed**

If the test fails, adjust `retrieve_candidates_node()` in `backend/app/agent/nodes.py` to keep this exact event payload:

```python
payload={
    "tool_name": response.tool_name,
    "provider": response.metadata.get("provider"),
    "fallback_provider": response.metadata.get("fallback_provider"),
    "fallback_reason": response.metadata.get("fallback_reason"),
}
```

Do not broaden node responsibilities beyond recording already-returned metadata.

- [ ] **Step 4: Run test to verify it passes**

Run the same focused command.

Expected: PASS.

## Task 5: Update README And Run Full Verification

**Files:**
- Modify: `backend/README.md`

- [ ] **Step 1: Update README truthfully**

Document only these new capabilities:

- optional `MCP_GATEWAY_PROVIDER=onesearch` gateway boundary
- OneSearch-compatible HTTP wrapper expected at `POST /search`
- `search_news` is the only OneSearch-backed tool in this slice
- provider failure degrades to deterministic local `mock_search`

Keep these non-claims explicit:

- no verified live OneSearch MCP deployment
- no raw MCP protocol session client
- no default free browsing path
- no production hardening guarantees

- [ ] **Step 2: Run focused tests**

Run:

```powershell
cd backend
py -3.12 -m pytest tests/test_tools_and_eval.py::test_settings_accept_onesearch_gateway_provider_values tests/test_tools_and_eval.py::test_onesearch_gateway_calls_wrapper_and_maps_results tests/test_tools_and_eval.py::test_onesearch_gateway_falls_back_to_local_mock_search_when_provider_fails tests/test_tools_and_eval.py::test_onesearch_gateway_delegates_non_search_tools_to_fallback_gateway tests/test_tools_and_eval.py::test_build_monitor_graph_uses_local_gateway_by_default tests/test_tools_and_eval.py::test_build_monitor_graph_uses_onesearch_gateway_when_configured tests/test_tools_and_eval.py::test_build_monitor_graph_degrades_to_local_gateway_when_onesearch_config_is_incomplete tests/test_monitor_run_flow.py::test_monitor_graph_records_onesearch_provider_fallback_event -q
```

Expected: PASS.

- [ ] **Step 3: Run full verification**

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

Expected:

- pytest passes without a live OneSearch service
- compile step succeeds
- diff check reports no whitespace errors
- compose config stays valid
- branch remains `feat/phase2-scheduler-worker`

- [ ] **Step 4: Commit and push**

```powershell
git add docs/superpowers/plans/2026-06-17-onesearch-mcp-boundary.md backend/app/core/config.py backend/app/mcp/gateway.py backend/app/mcp/onesearch_gateway.py backend/app/agent/graph.py backend/app/tools/registry.py backend/app/agent/nodes.py backend/tests/test_tools_and_eval.py backend/tests/test_monitor_run_flow.py backend/README.md
git commit -m "feat: add onesearch gateway boundary"
git push
```

## Self-Review

- Spec coverage:
  - settings boundary: Task 1
  - dedicated gateway adapter: Task 2
  - provider-aware graph build path: Task 3
  - fallback metadata and event visibility: Task 4
  - truthful README claims: Task 5
- Placeholder scan:
  - no `TODO`, `TBD`, or “similar to previous task” placeholders remain
- Type consistency:
  - `mcp_gateway_provider`, `onesearch_base_url`, `onesearch_timeout_seconds`, and `onesearch_max_results` are used consistently
  - provider metadata uses `provider`, `fallback_provider`, `used_fallback`, and `fallback_reason` consistently
