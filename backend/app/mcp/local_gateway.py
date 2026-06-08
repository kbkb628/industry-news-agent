from __future__ import annotations

from app.mcp.gateway import ToolCallable, ToolGateway
from app.tools.responses import ToolResponse


class LocalToolGateway(ToolGateway):
    def __init__(self) -> None:
        self._handlers: dict[str, ToolCallable] = {}

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
