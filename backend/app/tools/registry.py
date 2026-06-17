from __future__ import annotations

from typing import Any

from app.core.config import Settings
from app.llm.base import BaseLLMClient
from app.llm.mock_client import MockLLM
from app.mcp.gateway import ToolGateway
from app.tools.base import ToolHandler
from app.tools.browser_fetch_tool import BrowserFetchTool
from app.tools.dedup_tool import DedupCandidatesTool
from app.tools.extract_tool import ExtractCandidatesTool
from app.tools.push_tool import DecidePushTool
from app.tools.rss_tool import RSSCandidatesTool
from app.tools.scoring_tool import ScoreCandidatesTool
from app.tools.search_tool import (
    OpenWebSearchCandidatesTool,
    SearchCandidatesTool,
    SearchProviderFallbackTool,
)


class ToolRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, ToolHandler] = {}

    def register(self, tool_name: str, handler: ToolHandler) -> None:
        if tool_name in self._handlers:
            raise ValueError(f"Tool already registered: {tool_name}")
        self._handlers[tool_name] = handler

    def list_tool_names(self) -> list[str]:
        return list(self._handlers.keys())

    def register_into(self, gateway: ToolGateway) -> None:
        for tool_name, handler in self._handlers.items():
            gateway.register(tool_name, handler)


def _build_search_provider_tool(
    *,
    settings: Settings,
    search_http_client: Any | None = None,
) -> ToolHandler | None:
    if settings.search_provider != "open_websearch":
        return None
    if not settings.open_websearch_base_url:
        return None

    return SearchProviderFallbackTool(
        primary=OpenWebSearchCandidatesTool(
            base_url=settings.open_websearch_base_url,
            http_client=search_http_client,
            timeout_seconds=settings.open_websearch_timeout_seconds,
        ),
        fallback=SearchCandidatesTool(),
        provider_name="open_websearch",
    )


def build_default_tool_registry(
    *,
    llm: BaseLLMClient | None = None,
    settings: Settings | None = None,
    search_http_client: Any | None = None,
) -> ToolRegistry:
    resolved_llm = llm or MockLLM()
    registry = ToolRegistry()
    registry.register("rss_fetch", RSSCandidatesTool())
    registry.register("mock_search", SearchCandidatesTool())
    if settings is not None:
        search_provider_tool = _build_search_provider_tool(
            settings=settings,
            search_http_client=search_http_client,
        )
        if search_provider_tool is not None:
            registry.register("search_news", search_provider_tool)
    registry.register("fetch_article_content", BrowserFetchTool())
    registry.register("extract_article", ExtractCandidatesTool(llm=resolved_llm))
    registry.register("deduplicate_items", DedupCandidatesTool())
    registry.register("score_candidate", ScoreCandidatesTool(llm=resolved_llm))
    registry.register("decide_push", DecidePushTool())
    return registry
