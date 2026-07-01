from __future__ import annotations

from typing import Any

from app.core.config import Settings


def _build_tool_access_summary(settings: Settings | None) -> dict[str, Any]:
    search_access = "tool_gateway"
    if (
        settings is not None
        and settings.mcp_gateway_provider == "onesearch"
        and settings.onesearch_base_url
    ):
        search_access = "mcp_gateway"
    return {
        "contract": "unified_tool_gateway",
        "search": {
            "provider_path": search_access,
            "tool_name": "search_news",
        },
        "browser": {
            "provider_path": "tool_gateway",
            "tool_name": "fetch_article_content",
        },
        "notification": {
            "provider_path": "tool_gateway",
            "tool_name": "notification_send",
        },
    }


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
    browser_attempts = [
        item for item in fetched_contents if item.get("browser_attempted") is True
    ]
    blocked_browser_fetches = [
        item for item in browser_attempts if item.get("browser_allowed") is False
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
    browser_failure_reason = None
    if blocked_browser_fetches:
        browser_failure_reason = blocked_browser_fetches[0].get("browser_failure_reason")
    elif failed_browser_fetches:
        browser_failure_reason = failed_browser_fetches[0].get("browser_failure_reason")
    last_browser_provider = None
    if browser_attempts:
        last_browser_provider = browser_attempts[-1].get("browser_provider")

    notification_provider = "none" if settings is None else settings.notification_provider
    notification_enabled = False
    if settings is not None and settings.notification_provider == "webhook":
        notification_enabled = bool(settings.notification_webhook_url)
    notification_results = [
        item for item in tool_results if item.get("tool_name") == "notification_send"
    ]
    notification_failure = next(
        (
            item
            for item in notification_results
            if item.get("success") is False
        ),
        None,
    )
    notification_success = next(
        (
            item
            for item in notification_results
            if item.get("success") is True
        ),
        None,
    )
    notification_failure_code = None
    if notification_failure is not None:
        error = notification_failure.get("error")
        if isinstance(error, dict):
            notification_failure_code = error.get("code")
    if notification_failure_code is None and notification_failure is not None:
        notification_failure_code = notification_failure.get("error_code")

    return {
        "mcp": {
            "configured_provider": mcp_provider,
            "enabled": mcp_enabled,
            "selected_tool_path": "search_news",
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
            "selected_tool_path": "fetch_article_content.browser_fallback",
            "base_url_configured": browser_base_url_configured,
            "allowed_domains": allowed_domains,
            "used_in_run": bool(browser_fetches),
            "fallback_used": bool(browser_fetches or failed_browser_fetches),
            "fallback_reason": browser_fallback_reason,
            "browser_fetch_count": len(browser_fetches),
            "failed_browser_fetch_count": len(failed_browser_fetches),
            "browser_attempt_count": len(browser_attempts),
            "browser_blocked_count": len(blocked_browser_fetches),
            "browser_failure_reason": browser_failure_reason,
            "last_browser_provider": last_browser_provider,
        },
        "notification": {
            "configured_provider": notification_provider,
            "enabled": notification_enabled,
            "selected_tool_path": "notification_send",
            "used_in_run": bool(notification_results),
            "delivery_attempted": bool(notification_results),
            "delivery_succeeded": notification_success is not None,
            "fallback_used": False,
            "failure_code": notification_failure_code,
        },
        "tool_access": _build_tool_access_summary(settings),
    }
