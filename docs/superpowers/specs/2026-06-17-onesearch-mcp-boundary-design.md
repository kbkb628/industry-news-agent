# OneSearch MCP Boundary Design

## Purpose

Add a truthful Phase 2 integration boundary for OneSearch MCP without breaking
the deterministic MVP/Phase 2 baseline.

This slice exists to satisfy the `DEVELOPMENT_GUIDE.md` requirement that the
project retain a real MCP integration boundary beyond `LocalToolGateway`, while
still preserving:

- deterministic default behavior
- explicit degradation states
- Agent-node independence from a concrete third-party service

This design does not claim a verified live OneSearch MCP deployment. It defines
how the codebase should integrate an optional OneSearch-compatible path while
keeping the current fallback behavior visible and truthful.

## Current Context

The repository already has a stable tool-dispatch seam:

- `backend/app/mcp/gateway.py` defines the `ToolGateway` abstraction
- `backend/app/mcp/local_gateway.py` provides deterministic in-process handler
  registration
- `backend/app/agent/graph.py` builds a gateway and injects it into Agent nodes
- `backend/app/agent/nodes.py` calls tools through `gateway.call(...)`
- `backend/app/tools/registry.py` already supports optional provider wiring for
  OpenWebSearch, Playwright MCP-compatible browser fallback, OpenSearch history
  projection, and webhook notification

This means the codebase already has the correct architectural direction:
provider-specific logic belongs behind gateway/tool wiring, not inside Agent
nodes.

## Problem To Solve

The current project can truthfully claim:

- local `LocalToolGateway`
- optional OpenWebSearch-compatible HTTP search provider
- optional Playwright MCP-compatible browser-fetch provider

It cannot yet truthfully claim a OneSearch MCP gateway boundary, because:

- there is no dedicated OneSearch integration adapter
- no configuration explicitly selects a OneSearch-backed gateway path
- no error/event path identifies OneSearch unavailability as a distinct
  integration state

The next slice should fix that gap without reworking the entire tool system.

## Recommended Approach

Implement a `OneSearchMCPGateway` as an optional gateway adapter that talks to a
OneSearch-compatible HTTP wrapper service.

This is intentionally not a raw MCP transport client in this slice.

Why:

- It preserves the architectural boundary required by `DEVELOPMENT_GUIDE.md`
- It fits the current repository pattern, which already uses controlled HTTP
  adapters for optional provider paths
- It avoids coupling Agent nodes to a concrete MCP session protocol too early
- It keeps tests deterministic through fake HTTP clients and visible fallbacks

The HTTP wrapper is a transport choice, not a capability claim. The code should
describe it as a OneSearch-compatible integration boundary, not as proof of a
verified live MCP deployment.

## Non-Goals

This slice does not include:

- direct raw MCP protocol session management
- autonomous free browsing
- turning OneSearch into the default candidate retrieval path
- replacing `LocalToolGateway`
- removing `mock_search`
- changing Agent graph node semantics
- production hardening of a OneSearch deployment
- verified live third-party service availability claims

## Integration Shape

### Gateway Layer

The gateway layer should support two concrete paths:

- `LocalToolGateway`
- `OneSearchMCPGateway`

`LocalToolGateway` remains the default.

`OneSearchMCPGateway` should:

- implement the existing `ToolGateway` interface
- be selected only through explicit settings
- handle only the tool names intentionally mapped to OneSearch-backed behavior
- fall back to a local gateway for unsupported tools or provider failure

This keeps the gateway abstraction stable while allowing one gateway to delegate
to another.

### Tool Routing

The initial OneSearch integration should only target candidate retrieval.

The first version should map:

- `search_news`

to the OneSearch-backed path.

It should not move unrelated tools into the OneSearch provider path yet:

- `fetch_article_content`
- `extract_article`
- `deduplicate_items`
- `score_candidate`
- `decide_push`
- `notification_send`

These remain local/in-process tools.

This preserves the narrowest useful slice and avoids overstating OneSearch’s
role in the system.

### Transport Contract

The adapter should assume a OneSearch-compatible HTTP wrapper with a small,
explicit contract, for example:

- endpoint: `POST /search`
- request body:

```json
{
  "query": "AI Agent MCP LangGraph",
  "max_results": 10
}
```

- response body:

```json
{
  "results": [
    {
      "title": "Example title",
      "url": "https://example.com/story",
      "snippet": "Summary text",
      "source": "example.com",
      "published_at": "2026-06-17T10:00:00Z"
    }
  ]
}
```

This wrapper contract should be documented as an integration boundary, not as a
claim that the upstream OneSearch service exposes this exact HTTP surface
directly.

## Fallback And Failure Rules

Failure handling is the core requirement of this slice.

If OneSearch is configured but unavailable, the system must:

1. return a valid `ToolResponse`
2. record provider metadata and fallback reason
3. continue with deterministic local fallback behavior
4. expose the degradation through events/errors/metadata

Expected fallback behavior:

- primary provider: OneSearch-compatible wrapper
- fallback provider: `mock_search`

Expected metadata shape:

```json
{
  "provider": "onesearch_mcp",
  "fallback_provider": "mock_search",
  "used_fallback": true,
  "fallback_reason": "connection refused"
}
```

If OneSearch is not configured at all, the system should not pretend the
provider exists. In that case, registry/gateway construction should simply stay
on the local deterministic path.

## Settings Boundary

The first implementation should add explicit settings for the gateway path, for
example:

- `MCP_GATEWAY_PROVIDER=local|onesearch`
- `ONESEARCH_BASE_URL`
- `ONESEARCH_TIMEOUT_SECONDS`
- `ONESEARCH_MAX_RESULTS`

Rules:

- default provider is `local`
- `onesearch` provider is only active when `ONESEARCH_BASE_URL` is configured
- incomplete OneSearch settings must degrade to local behavior
- settings should not silently claim a live provider path when configuration is
  incomplete

This settings pattern should align with the existing optional-provider patterns
already present in the repository.

## Agent And Graph Boundary

Agent nodes must remain unchanged in their core interaction pattern:

- nodes call `gateway.call(tool_name, ...)`
- nodes inspect `ToolResponse`
- nodes record errors/fallbacks through the existing event path

The graph should not learn OneSearch-specific logic.

Instead:

- gateway construction becomes provider-aware
- registry wiring becomes provider-aware
- node behavior remains provider-agnostic

This boundary is mandatory. If a design requires Agent nodes to branch on
OneSearch-specific transport behavior, the design is wrong.

## Testing Strategy

The first implementation must stay deterministic and testable without a live
OneSearch service.

Required test coverage:

- settings accept OneSearch gateway configuration
- provider-aware gateway builder selects local or OneSearch path correctly
- OneSearch adapter converts wrapper results into current candidate schema
- provider failure falls back to local deterministic search behavior
- fallback metadata is preserved in `ToolResponse`
- monitor flow records fallback visibility rather than swallowing it

Tests should use fake HTTP clients, following the same style already used for:

- OpenWebSearch-compatible provider tests
- Playwright MCP-compatible browser fetch tests
- webhook notification tests

## README And Capability Claims

README updates for this slice must be explicit and narrow.

Allowed claims:

- optional OneSearch-compatible MCP gateway boundary
- local deterministic fallback remains default-safe
- OneSearch provider failures degrade visibly to local search behavior

Forbidden claims:

- verified live OneSearch MCP deployment
- raw MCP protocol client completeness
- production search reliability
- production MCP fleet management
- broader browsing or extraction capabilities not actually implemented

## Acceptance Criteria

This slice is acceptable when:

- the codebase can be configured to prefer a OneSearch-backed gateway path
- the default path remains deterministic and local
- OneSearch wrapper failures degrade to local fallback without masking the
  failure
- provider metadata and fallback reasons are visible in `ToolResponse` and run
  state/event evidence
- backend tests pass without a live OneSearch service
- README remains truthful about what is and is not implemented

## Recommended Next Step

Write a detailed implementation plan for the OneSearch MCP boundary using the
`HTTP wrapper adapter + ToolGateway fallback` approach.

That plan should stay narrowly scoped to:

- settings
- gateway adapter
- provider-aware registry/build path
- focused tests
- README truthfulness
