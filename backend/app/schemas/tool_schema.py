from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ToolError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    fallback: str | None = None


class ToolExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: bool
    tool_name: str
    data: dict[str, Any] | list[Any] | None = None
    summary: str
    error: ToolError | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
