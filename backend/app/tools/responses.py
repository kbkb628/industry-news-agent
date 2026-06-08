from __future__ import annotations

from typing import Any


class ToolErrorDetail:
    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.details = details or {}


class ToolResponse:
    def __init__(
        self,
        *,
        success: bool,
        tool_name: str,
        summary: str,
        data: dict[str, Any] | list[Any] | None = None,
        error: ToolErrorDetail | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if success and error is not None:
            raise ValueError("ToolResponse cannot use success=True with error!=None.")
        if not success and error is None:
            raise ValueError("ToolResponse cannot use success=False with error=None.")

        self.success = success
        self.tool_name = tool_name
        self.summary = summary
        self.data = data
        self.error = error
        self.metadata = metadata or {}

    @classmethod
    def success(
        cls,
        tool_name: str,
        summary: str,
        data: dict[str, Any] | list[Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "ToolResponse":
        return cls(
            success=True,
            tool_name=tool_name,
            summary=summary,
            data=data,
            metadata=metadata,
        )

    @classmethod
    def failure(
        cls,
        tool_name: str,
        code: str,
        message: str,
        summary: str,
        details: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "ToolResponse":
        return cls(
            success=False,
            tool_name=tool_name,
            summary=summary,
            error=ToolErrorDetail(code=code, message=message, details=details),
            metadata=metadata,
        )
