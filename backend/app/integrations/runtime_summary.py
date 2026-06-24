from __future__ import annotations

from typing import Any

from app.core.config import Settings


def build_integration_runtime(
    *,
    settings: Settings | None,
    tool_results: list[dict[str, Any]],
    fetched_contents: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    mcp_provider = None if settings is None else settings.mcp_gateway_provider
    mcp_base_url_configured = bool(settings and settings.onesearch_base_url)
    mcp_enabled = bool(
        settings
        and settings.mcp_gateway_provider == "onesearch"
        and settings.onesearch_base_url
    )
    mcp_tool_results = [
        item
        for item in tool_results
        if item.get("tool_name") == "search_news"
        and isinstance(item.get("metadata"), dict)
        and item["metadata"].get("provider") == "onesearch_mcp"
    ]
    mcp_fallback_result = next(
        (
            item
            for item in mcp_tool_results
            if item["metadata"].get("used_fallback") is True
        ),
        None,
    )

    browser_provider = None if settings is None else settings.browser_fetch_provider
    allowed_domains = [] if settings is None else list(settings.browser_allowed_domains)
    browser_base_url_configured = bool(settings and settings.playwright_mcp_base_url)
    browser_enabled = bool(
        settings
        and settings.browser_fetch_provider == "playwright_mcp"
        and settings.playwright_mcp_base_url
        and settings.browser_allowed_domains
    )
    browser_fetches = [
        item for item in fetched_contents if item.get("fetch_method") == "browser_fallback"
    ]
    failed_browser_fetches = [
        item
        for item in fetched_contents
        if item.get("fetch_status") == "failed"
        and item.get("fetch_fallback_reason")
    ]
    browser_fallback_reason = None
    if browser_fetches:
        browser_fallback_reason = browser_fetches[0].get("fetch_fallback_reason")
    elif failed_browser_fetches:
        browser_fallback_reason = failed_browser_fetches[0].get("fetch_fallback_reason")

    return {
        "mcp": {
            "configured_provider": mcp_provider,
            "enabled": mcp_enabled,
            "selected_tool_path": "onesearch_mcp" if mcp_enabled else "local_gateway",
            "base_url_configured": mcp_base_url_configured,
            "used_in_run": bool(mcp_tool_results),
            "fallback_used": mcp_fallback_result is not None,
            "fallback_provider": (
                None
                if mcp_fallback_result is None
                else mcp_fallback_result["metadata"].get("fallback_provider")
            ),
            "fallback_reason": (
                None
                if mcp_fallback_result is None
                else mcp_fallback_result["metadata"].get("fallback_reason")
            ),
            "tool_call_count": len(mcp_tool_results),
        },
        "browser": {
            "configured_provider": browser_provider,
            "enabled": browser_enabled,
            "selected_tool_path": "playwright_mcp" if browser_enabled else "http",
            "base_url_configured": browser_base_url_configured,
            "allowed_domains": allowed_domains,
            "used_in_run": bool(browser_fetches),
            "fallback_used": bool(browser_fetches or failed_browser_fetches),
            "fallback_reason": browser_fallback_reason,
            "browser_fetch_count": len(browser_fetches),
            "failed_browser_fetch_count": len(failed_browser_fetches),
        },
    }
