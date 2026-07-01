from __future__ import annotations

from typing import Any

from app.mcp.gateway import (
    ToolCallable,
    ToolGateway,
    build_unified_tool_access_contract,
)
from app.tools.responses import ToolResponse


class LocalToolGateway(ToolGateway):
    def __init__(self, *, tool_access_contract: dict[str, Any] | None = None) -> None:
        self._handlers: dict[str, ToolCallable] = {}
        self._tool_access_contract = (
            build_unified_tool_access_contract()
            if tool_access_contract is None
            else dict(tool_access_contract)
        )

    def register(self, tool_name: str, handler: ToolCallable) -> None:
        if tool_name in self._handlers:
            raise ValueError(f"Tool already registered: {tool_name}")
        self._handlers[tool_name] = handler

    def call(self, tool_name: str, **kwargs: object) -> ToolResponse:
        handler = self._handlers.get(tool_name)
        if handler is None:
            return ToolResponse.failure(
                tool_name=tool_name,
                code="tool_not_registered",
                message=f"Tool '{tool_name}' is not registered.",
                summary="Local tool lookup failed",
            )

        try:
            result = handler(**kwargs)
        except Exception as exc:
            return ToolResponse.failure(
                tool_name=tool_name,
                code="tool_execution_failed",
                message=str(exc),
                summary="Local tool execution failed",
            )

        if not isinstance(result, ToolResponse):
            return ToolResponse.failure(
                tool_name=tool_name,
                code="invalid_tool_response",
                message=(
                    f"Tool '{tool_name}' returned {type(result).__name__} "
                    "instead of ToolResponse."
                ),
                summary="Local tool returned an invalid response",
            )

        return result

    def describe_tool_access(self) -> dict[str, Any]:
        return {
            key: dict(value) if isinstance(value, dict) else value
            for key, value in self._tool_access_contract.items()
        }
