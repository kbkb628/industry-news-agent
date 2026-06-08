from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeAlias

from app.tools.responses import ToolResponse

ToolHandler: TypeAlias = Callable[..., ToolResponse]

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "data" / "fixtures"
SOURCES_FIXTURE_PATH = FIXTURE_DIR / "sample_sources.json"
ARTICLES_FIXTURE_PATH = FIXTURE_DIR / "sample_articles.json"


def load_json_fixture(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def canonicalize_url(url: str) -> str:
    normalized = url.strip().lower()
    normalized = re.sub(r"#.*$", "", normalized)
    normalized = re.sub(r"\?.*$", "", normalized)
    return normalized.rstrip("/")


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.lower())).strip()


def content_fingerprint(*, content: str, raw_summary: str | None = None) -> str:
    payload_source = content if normalize_text(content) else (raw_summary or "")
    payload = normalize_text(payload_source)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def fixture_sources(path: Path = SOURCES_FIXTURE_PATH) -> list[dict[str, Any]]:
    return list(load_json_fixture(path).get("sources", []))


def fixture_articles(path: Path = ARTICLES_FIXTURE_PATH) -> list[dict[str, Any]]:
    return list(load_json_fixture(path).get("articles", []))


class FixtureTool:
    def __init__(
        self,
        tool_name: str,
        *,
        sources_path: Path = SOURCES_FIXTURE_PATH,
        articles_path: Path = ARTICLES_FIXTURE_PATH,
    ) -> None:
        self.tool_name = tool_name
        self.sources_path = sources_path
        self.articles_path = articles_path

    def load_sources(self) -> list[dict[str, Any]]:
        return fixture_sources(self.sources_path)

    def load_articles(self) -> list[dict[str, Any]]:
        return fixture_articles(self.articles_path)

    def success(
        self,
        *,
        summary: str,
        data: dict[str, Any] | list[Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ToolResponse:
        return ToolResponse.success(
            tool_name=self.tool_name,
            summary=summary,
            data=data,
            metadata=metadata,
        )

    def failure(
        self,
        *,
        code: str,
        message: str,
        summary: str,
        details: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ToolResponse:
        return ToolResponse.failure(
            tool_name=self.tool_name,
            code=code,
            message=message,
            summary=summary,
            details=details,
            metadata=metadata,
        )
