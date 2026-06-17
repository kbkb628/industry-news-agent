from __future__ import annotations

from collections.abc import Callable
from threading import BoundedSemaphore
from typing import Any
from urllib.parse import urlparse

try:
    import httpx
except ImportError:  # pragma: no cover - fallback only matters outside tests.
    httpx = None

from app.tools.base import FixtureTool, canonicalize_url


class PlaywrightMCPBrowserFetcher:
    def __init__(
        self,
        *,
        base_url: str,
        allowed_domains: list[str],
        http_client: Any | None = None,
        timeout_seconds: float = 10.0,
        max_concurrency: int = 1,
        max_content_chars: int = 20000,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.allowed_domains = tuple(domain.lower() for domain in allowed_domains)
        self.http_client = http_client
        self.timeout_seconds = timeout_seconds
        self._semaphore = BoundedSemaphore(max(1, max_concurrency))
        self.max_content_chars = max_content_chars

    def __call__(self, url: str) -> str:
        self._validate_allowed_url(url)
        client = self.http_client
        if client is None:
            if httpx is None:
                raise RuntimeError("httpx is unavailable for Playwright MCP fetches.")
            client = httpx

        with self._semaphore:
            response = client.post(
                f"{self.base_url}/fetch",
                json={"url": url},
                timeout=self.timeout_seconds,
            )
        response.raise_for_status()
        payload = response.json()
        content = payload.get("content") or payload.get("text") or payload.get("markdown")
        if not isinstance(content, str):
            raise RuntimeError("Playwright MCP response did not include text content.")
        return content[: self.max_content_chars]

    def _validate_allowed_url(self, url: str) -> None:
        host = (urlparse(url).hostname or "").lower()
        if not host:
            raise ValueError("Browser fetch URL must include a host.")
        if not any(
            host == domain or host.endswith(f".{domain}")
            for domain in self.allowed_domains
        ):
            raise ValueError(f"Browser fetch domain is not allowed: {host}")


class BrowserFetchTool(FixtureTool):
    def __init__(
        self,
        *,
        fetcher: Callable[[str], str] | None = None,
        browser_fetcher: Callable[[str], str] | None = None,
        browser_provider: str | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        super().__init__("fetch_article_content")
        self.fetcher = fetcher
        self.browser_fetcher = browser_fetcher
        self.browser_provider = browser_provider
        self.timeout_seconds = timeout_seconds

    def __call__(self, *, candidates: list[dict[str, Any]]) -> object:
        article_by_candidate_id = {
            str(article["candidate_id"]): article for article in self.load_articles()
        }
        article_by_url = {
            canonicalize_url(article["url"]): article for article in self.load_articles()
        }
        fetched_candidates: list[dict[str, Any]] = []
        used_browser_fallback = False

        for candidate in candidates:
            resolved = dict(candidate)
            article = article_by_candidate_id.get(str(candidate["candidate_id"]))
            if article is None:
                article = article_by_url.get(canonicalize_url(str(candidate["url"])))

            try:
                if article is not None:
                    content = str(article.get("content", ""))
                    resolved["fetch_method"] = "fixture"
                elif self.fetcher is not None:
                    content = self.fetcher(str(candidate["url"]))
                    resolved["fetch_method"] = "http"
                elif httpx is not None:
                    response = httpx.get(
                        str(candidate["url"]),
                        follow_redirects=True,
                        timeout=self.timeout_seconds,
                    )
                    response.raise_for_status()
                    content = response.text
                    resolved["fetch_method"] = "http"
                else:
                    raise RuntimeError("httpx is unavailable for remote fetches.")

                resolved["fetch_status"] = "fetched"
                resolved["content"] = content
            except Exception as exc:
                if self.browser_fetcher is not None:
                    try:
                        resolved["content"] = self.browser_fetcher(str(candidate["url"]))
                        resolved["fetch_status"] = "fetched"
                        resolved["fetch_method"] = "browser_fallback"
                        resolved["fetch_fallback_reason"] = str(exc)
                        used_browser_fallback = True
                    except Exception as fallback_exc:
                        resolved["fetch_status"] = "failed"
                        resolved["content"] = ""
                        resolved["fetch_error"] = str(fallback_exc)
                        resolved["fetch_fallback_reason"] = str(exc)
                else:
                    resolved["fetch_status"] = "failed"
                    resolved["content"] = ""
                    resolved["fetch_error"] = str(exc)

            fetched_candidates.append(resolved)

        return self.success(
            summary=f"Fetched {len(fetched_candidates)} candidate page(s).",
            data={"candidates": fetched_candidates},
            metadata={
                "used_browser_fallback": used_browser_fallback,
                "browser_provider": self.browser_provider,
            },
        )
