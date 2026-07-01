from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from app.tools.responses import ToolResponse

ToolCallable = Callable[..., ToolResponse]


def build_unified_tool_access_contract(
    *,
    search_provider_path: str = "tool_gateway",
    browser_provider_path: str = "tool_gateway",
    notification_provider_path: str = "tool_gateway",
) -> dict[str, Any]:
    return {
        "contract": "unified_tool_gateway",
        "search": {
            "provider_path": search_provider_path,
            "tool_name": "search_news",
        },
        "browser": {
            "provider_path": browser_provider_path,
            "tool_name": "fetch_article_content",
        },
        "notification": {
            "provider_path": notification_provider_path,
            "tool_name": "notification_send",
        },
    }


def build_tool_access_metadata(
    contract: dict[str, Any],
    *,
    capability: str,
) -> dict[str, Any]:
    capability_entry = dict(contract.get(capability, {}))
    return {
        "contract": str(contract.get("contract", "unified_tool_gateway")),
        "capability": capability,
        "provider_path": str(capability_entry.get("provider_path", "tool_gateway")),
        "tool_name": str(capability_entry.get("tool_name", "")),
    }


class ToolGateway(ABC):
    @abstractmethod
    def register(self, tool_name: str, handler: ToolCallable) -> None:
        """Register a local tool handler."""

    @abstractmethod
    def call(self, tool_name: str, **kwargs: object) -> ToolResponse:
        """Execute a registered local tool."""

    @abstractmethod
    def describe_tool_access(self) -> dict[str, Any]:
        """Describe the unified tool-access contract exposed by this gateway."""
