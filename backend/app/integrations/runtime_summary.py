from __future__ import annotations

from typing import Any

from app.core.config import Settings
from app.mcp.gateway import ToolGateway


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


def _build_tool_call_evidence(
    tool_results: list[dict[str, Any]],
    *,
    tool_name: str,
    fallback_metadata_keys: tuple[str, ...] = ("used_fallback",),
) -> dict[str, Any]:
    matching_results = [
        item for item in tool_results if item.get("tool_name") == tool_name
    ]
    success_count = sum(1 for item in matching_results if item.get("success") is True)
    failure_count = sum(1 for item in matching_results if item.get("success") is False)
    fallback_used = any(
        isinstance(item.get("metadata"), dict)
        and any(item["metadata"].get(key) is True for key in fallback_metadata_keys)
        for item in matching_results
    )
    return {
        "used_in_run": bool(matching_results),
        "tool_call_count": len(matching_results),
        "success_count": success_count,
        "failure_count": failure_count,
        "fallback_used": fallback_used,
    }


def _build_tool_access_contract_from_results(
    tool_results: list[dict[str, Any]],
) -> dict[str, Any] | None:
    contract = None
    capability_entries: dict[str, dict[str, Any]] = {}
    for item in tool_results:
        metadata = item.get("metadata")
        if not isinstance(metadata, dict):
            continue
        access = metadata.get("access")
        if not isinstance(access, dict):
            continue
        capability = access.get("capability")
        if not isinstance(capability, str) or not capability:
            continue
        if contract is None and isinstance(access.get("contract"), str):
            contract = access["contract"]
        capability_entries[capability] = {
            "provider_path": access.get("provider_path"),
            "tool_name": access.get("tool_name"),
        }

    if contract is None or not capability_entries:
        return None

    result: dict[str, Any] = {"contract": contract}
    for capability in ("search", "browser", "notification"):
        if capability in capability_entries:
            result[capability] = dict(capability_entries[capability])
    return result


def _build_tool_access_calls(
    tool_results: list[dict[str, Any]],
    *,
    contract: dict[str, Any],
) -> list[dict[str, Any]]:
    tool_name_to_capability: dict[str, str] = {}
    for capability in ("search", "browser", "notification"):
        entry = contract.get(capability)
        if isinstance(entry, dict):
            tool_name = entry.get("tool_name")
            if isinstance(tool_name, str) and tool_name:
                tool_name_to_capability[tool_name] = capability

    calls: list[dict[str, Any]] = []
    for item in tool_results:
        tool_name = item.get("tool_name")
        if not isinstance(tool_name, str) or not tool_name:
            continue

        metadata = item.get("metadata")
        metadata_dict = metadata if isinstance(metadata, dict) else {}
        access = metadata_dict.get("access")
        access_dict = access if isinstance(access, dict) else {}
        capability = access_dict.get("capability")
        if not isinstance(capability, str) or not capability:
            capability = tool_name_to_capability.get(tool_name)
        if capability not in ("search", "browser", "notification"):
            continue

        provider_path = access_dict.get("provider_path")
        if not isinstance(provider_path, str) or not provider_path:
            provider_path = str(
                dict(contract.get(capability, {})).get("provider_path", "tool_gateway")
            )

        provider = None
        if capability == "search":
            provider = metadata_dict.get("provider")
        elif capability == "browser":
            provider = metadata_dict.get("browser_provider")
        elif capability == "notification":
            provider = metadata_dict.get("notification_provider")

        error = item.get("error")
        error_code = None
        if isinstance(error, dict):
            error_code = error.get("code")
        if error_code is None:
            error_code = item.get("error_code")

        calls.append(
            {
                "capability": capability,
                "tool_name": tool_name,
                "provider_path": provider_path,
                "provider": provider,
                "success": item.get("success") is True,
                "fallback_used": bool(
                    metadata_dict.get("used_fallback") is True
                    or metadata_dict.get("used_browser_fallback") is True
                ),
                "error_code": error_code,
            }
        )

    return calls


def _attach_tool_call_evidence(
    contract: dict[str, Any],
    *,
    tool_results: list[dict[str, Any]],
) -> dict[str, Any]:
    enriched = {
        key: dict(value) if isinstance(value, dict) else value
        for key, value in contract.items()
    }
    capability_specs = {
        "search": {
            "tool_name": "search_news",
            "fallback_metadata_keys": ("used_fallback",),
        },
        "browser": {
            "tool_name": "fetch_article_content",
            "fallback_metadata_keys": ("used_fallback", "used_browser_fallback"),
        },
        "notification": {
            "tool_name": "notification_send",
            "fallback_metadata_keys": ("used_fallback",),
        },
    }
    for capability, spec in capability_specs.items():
        current_entry = dict(enriched.get(capability, {}))
        current_entry.update(
            _build_tool_call_evidence(
                tool_results,
                tool_name=str(spec["tool_name"]),
                fallback_metadata_keys=tuple(spec["fallback_metadata_keys"]),
            )
        )
        enriched[capability] = current_entry
    enriched["calls"] = _build_tool_access_calls(tool_results, contract=enriched)
    return enriched


def _build_judge_runtime(
    settings: Settings | None,
    eval_result: dict[str, Any] | None,
) -> dict[str, Any]:
    result = eval_result if isinstance(eval_result, dict) else {}
    raw_issues = result.get("judge_issues")
    issues = [str(item) for item in raw_issues] if isinstance(raw_issues, list) else []

    mode = result.get("judge_mode")
    if not isinstance(mode, str) or not mode:
        mode = None

    reason = result.get("judge_reason")
    if not isinstance(reason, str) or not reason:
        reason = None

    configured_provider = "mock" if settings is None else settings.judge_provider
    selected_model = None
    if settings is not None and settings.judge_provider == "openai_compatible":
        selected_model = settings.judge_model

    return {
        "configured_provider": configured_provider,
        "enabled": bool(
            settings
            and settings.judge_provider == "openai_compatible"
            and settings.judge_base_url
            and settings.judge_api_key
        ),
        "selected_model": selected_model,
        "base_url_configured": bool(settings and settings.judge_base_url),
        "used_in_run": bool(result),
        "fallback_used": "judge_provider_fallback" in issues,
        "mode": mode,
        "issue_count": len(issues),
        "reason": reason,
    }


def build_integration_runtime(
    *,
    settings: Settings | None,
    gateway: ToolGateway | None = None,
    tool_results: list[dict[str, Any]],
    fetched_contents: list[dict[str, Any]],
    eval_result: dict[str, Any] | None = None,
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
        "judge": _build_judge_runtime(settings, eval_result),
        "tool_access": _attach_tool_call_evidence(
            (
                _build_tool_access_contract_from_results(tool_results)
                or (
                    gateway.describe_tool_access()
                    if gateway is not None
                    else _build_tool_access_summary(settings)
                )
            ),
            tool_results=tool_results,
        ),
    }
