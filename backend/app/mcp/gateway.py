from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

from app.tools.responses import ToolResponse

ToolCallable = Callable[..., ToolResponse]


class ToolGateway(ABC):
    @abstractmethod
    def register(self, tool_name: str, handler: ToolCallable) -> None:
        """Register a local tool handler."""

    @abstractmethod
    def call(self, tool_name: str, **kwargs: object) -> ToolResponse:
        """Execute a registered local tool."""
