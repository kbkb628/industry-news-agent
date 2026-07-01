# Unified Tool Gateway Contract Design

**Goal:** Make the existing unified tool-access claim more real by moving the
contract source from display-time inference into the gateway layer itself.

**Scope:** This design only tightens the current `search_news`,
`fetch_article_content`, and `notification_send` access contract. It does not
add new providers, does not claim browser or notification are MCP-backed, and
does not broaden the system into a generic MCP platform.

## Current State

The project already routes all three tool families through a shared
`gateway.call(...)` entry point. That means the "unified gateway" part of the
resume claim is already true at execution time.

The remaining weakness is that `integration_runtime.tool_access` is still
derived mostly from `settings`, not from a first-class gateway contract. That
keeps the claim at a partial level because the read surface is summarizing a
fact that the gateway itself does not expose directly.

## Design

Add a read-only access-contract method to `ToolGateway` that returns a stable
summary for:

- `contract`
- `search`
- `browser`
- `notification`

Each capability entry should expose:

- `tool_name`
- `provider_path`
- `configured_provider`
- `selected_tool_path`

The gateway remains truthful:

- `LocalToolGateway` reports all three capabilities on `tool_gateway`
- `OneSearchMCPGateway` reports only `search` on `mcp_gateway`
- `browser` and `notification` remain on `tool_gateway`

`integration_runtime.tool_access` should prefer this gateway-provided contract
when a gateway is available, and only fall back to settings-based inference
when a gateway object is absent.

## Non-Goals

- No new provider adapters
- No browser MCP generalization
- No notification MCP path
- No schema or persistence expansion beyond the runtime snapshot contract

## Verification

The implementation is complete when:

1. gateway-level tests prove the contract is exposed by both gateway types
2. runtime-summary tests prove `tool_access` is derived from the gateway when
   available
3. run snapshot tests still show the same truthful provider-path split in
   `integration_runtime.tool_access`
