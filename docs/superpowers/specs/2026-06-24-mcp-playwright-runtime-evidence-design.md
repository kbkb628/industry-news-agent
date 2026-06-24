# MCP And Playwright Runtime Evidence Design

**Goal:** Upgrade the existing MCP and browser-fallback boundaries into a
truthful, executable runtime slice with visible configuration, visible fallback
behavior, and visible run evidence that stays within the resume and
`DEVELOPMENT_GUIDE.md` boundaries.

**Scope:** This design covers only the existing `OneSearchMCPGateway` path for
`search_news`, the existing `PlaywrightMCPBrowserFetcher` fallback path for
`fetch_article_content`, and the API/UI/runtime evidence needed to prove those
paths are real when configured. It does not add new providers, unconstrained
browser automation, or broaden the project into a general MCP platform.

**Why now:** Phase A foundations are complete. The next resume-listed
technologies still sitting at a boundary level are `MCP` and `Playwright`. The
repo already contains truthful adapters, but it still lacks a narrow end-to-end
runtime slice that proves when those adapters are actually configured, when
they are used, when they degrade, and how an operator can verify that from the
project itself.

---

## 1. Current State

The repository already contains the correct architectural direction:

- `backend/app/mcp/onesearch_gateway.py` wraps a OneSearch-compatible MCP
  search path with local fallback
- `backend/app/tools/browser_fetch_tool.py` keeps browser access as a final
  fallback after fixture and plain HTTP fetch
- `backend/app/tools/registry.py` and `backend/app/agent/graph.py` wire both
  paths conditionally from settings
- retrieval and extraction agents already emit `fallback_used` events and store
  serialized tool results
- README already documents the optional configuration surface conservatively

Current limitations:

- there is no dedicated runtime summary that states which MCP/browser provider
  path was actually active for a given run
- tool results keep raw metadata, but the run snapshot and HTML surfaces do not
  turn that into an operator-friendly proof surface
- fallback evidence is visible in events, but the system does not expose a
  compact per-run summary such as provider selected, provider used, provider
  degraded, and affected candidate counts
- tests prove adapters and fallback semantics, but they do not yet prove a
  coherent configured-path story from settings through run snapshot and HTML
  evidence
- the current resume-alignment page still has to describe MCP and browser
  execution as boundaries because the repo does not yet make runtime proof easy

This slice fixes those gaps without overstating actual deployment truth.

## 2. Design Principles

The implementation must preserve these rules:

1. Keep browser access as the last fallback path, never the default fetch path.
2. Do not claim general live MCP session orchestration or broad tool discovery.
3. Do not add a new provider or a second MCP story.
4. Keep the existing `onesearch` and `playwright_mcp` contracts, and make them
   easier to verify.
5. Failure and fallback must stay visible in state, events, and UI.
6. The project may prove an executable runtime path without pretending the
   external service is always available in every environment.

## 3. Target Runtime Evidence Contract

Each monitor run should expose a compact runtime evidence section describing the
selected MCP and browser-fallback paths.

Target state shape:

```json
{
  "integration_runtime": {
    "mcp": {
      "configured_provider": "onesearch",
      "enabled": true,
      "selected_tool_path": "search_news",
      "base_url_configured": true,
      "used_in_run": true,
      "fallback_used": false,
      "fallback_provider": null,
      "fallback_reason": null,
      "tool_call_count": 1
    },
    "browser": {
      "configured_provider": "playwright_mcp",
      "enabled": true,
      "selected_tool_path": "fetch_article_content.browser_fallback",
      "base_url_configured": true,
      "allowed_domains": ["example.com", "news.example.com"],
      "used_in_run": true,
      "fallback_used": true,
      "fallback_reason": "HTTP 403",
      "browser_fetch_count": 1,
      "failed_browser_fetch_count": 0
    }
  }
}
```

Contract rules:

- `configured_provider` describes configuration, not observed success
- `enabled` is true only when the configuration required for that provider is
  complete
- `used_in_run` means the provider path was actually exercised during the run
- `fallback_used` means the system had to degrade to a lower-priority provider
  or the browser fallback path was activated after plain HTTP failed
- missing configuration must result in a truthful disabled state, not a fake
  success or silent provider substitution

## 4. MCP Runtime Slice

This project does not need generic MCP lifecycle management for the resume
claim. It needs one real MCP-backed runtime path that is configured, executed,
normalized, and visible.

### 4.1 In-Scope MCP Path

The only in-scope MCP path for this slice is:

- `search_news` through `OneSearchMCPGateway`

The gateway remains a compatibility wrapper around a OneSearch-compatible HTTP
surface. That is acceptable as long as the project is explicit that:

- the runtime path is real when configured
- search calls normalize back into project candidate contracts
- fallback to local search is visible when the provider fails

### 4.2 MCP Evidence Requirements

When `MCP_GATEWAY_PROVIDER=onesearch` and `ONESEARCH_BASE_URL` is configured:

- the run snapshot must show that the MCP path was enabled
- serialized tool results must show provider metadata
- retrieval-stage events must show whether the MCP path succeeded or degraded
- the run detail UI must summarize whether MCP was configured, used, and
  degraded

When configuration is incomplete:

- the snapshot must show the MCP path as disabled
- the local gateway remains the runtime default
- the project must not claim this run used MCP

### 4.3 MCP Failure Semantics

If the OneSearch provider fails:

- retrieval continues through local fallback
- `tool_results` preserves provider metadata and fallback reason
- a `fallback_used` event remains persisted
- the runtime evidence summary must show:
  - MCP configured: yes
  - MCP used in run: yes
  - MCP degraded to fallback: yes
  - fallback provider: `mock_search`

## 5. Playwright Runtime Slice

This project should not present Playwright as a default crawler or free-form
browser agent. It should present it as a governed last-mile retrieval fallback.

### 5.1 In-Scope Browser Path

The only in-scope browser path for this slice is:

- `fetch_article_content` -> plain HTTP attempt
- on failure, optional `PlaywrightMCPBrowserFetcher`

This preserves the development-guide strategy:

- fixtures/local content first
- plain HTTP second
- browser fallback last

### 5.2 Browser Evidence Requirements

When `BROWSER_FETCH_PROVIDER=playwright_mcp`,
`PLAYWRIGHT_MCP_BASE_URL`, and `BROWSER_ALLOWED_DOMAINS` are configured:

- the run snapshot must show browser fallback as enabled
- extraction evidence must show whether browser fallback was actually used
- the runtime evidence summary must show allowed domains and browser fetch
  counts
- run detail UI must summarize that browser fetch is a governed fallback path,
  not the default strategy

When configuration is incomplete:

- browser fallback remains disabled
- failed HTTP fetches stay visible as failed or raw-summary-based extractions
- the run snapshot must not imply Playwright was used

### 5.3 Browser Failure Semantics

If plain HTTP fails and browser fallback is configured:

- browser fallback attempts are allowed only for domains inside the configured
  allowlist
- successful fallback should increment a browser-fetch usage count
- failed fallback should remain visible through candidate fetch status, errors,
  and runtime evidence summary

If the domain is not allowed or the browser provider fails:

- the candidate must remain degraded or failed
- the snapshot must preserve the reason
- the project must not present the candidate as fully fetched

## 6. Runtime Summary Derivation

The project already stores enough raw evidence in `tool_results`, candidate
fetch metadata, and events. This slice should derive a stable summary instead of
introducing a second persistence system.

Recommended derivation inputs:

- `Settings`
- `state["tool_results"]`
- `state["retrieval_output"]["provider_fallbacks"]`
- `state["extraction_output"]["content_fallbacks"]`
- candidate fetch results in `fetched_contents`

Recommended derived outputs:

- MCP enabled/configured/used/fallback summary
- browser enabled/configured/used/fallback summary
- browser allowed domains snapshot
- candidate counts affected by browser fallback

This derived section may live only inside `state_snapshot` for this slice. No
relational schema change is required.

## 7. API And Compatibility Strategy

The existing `GET /api/monitor/runs/{run_id}` compatibility snapshot should
gain:

- `integration_runtime`

Compatibility rules:

- keep all existing top-level snapshot fields
- do not remove raw `tool_results`, because they remain the low-level audit
  surface
- `integration_runtime` becomes the compact operator-friendly proof surface

The candidate and events endpoints do not need a contract redesign for this
slice. They only need to remain consistent with the new summary.

## 8. HTML Evidence Surface

The minimal HTML admin surface should become better at proving runtime truth.

### 8.1 Run Detail Page

`GET /runs/{run_id}` should show:

- MCP configured provider
- whether MCP was used in the run
- whether MCP degraded to fallback
- browser fallback configured provider
- browser allowlist snapshot
- whether browser fallback was used
- whether the browser path failed for any candidate

The page should explain the strategy in plain terms:

- search may use MCP when configured
- browser remains a final fallback after HTTP failure

### 8.2 Resume Alignment Page

`GET /resume-alignment` or equivalent resume-facing copy should move from a
pure boundary statement to a narrower truthful statement:

- MCP and Playwright have real optional runtime paths with explicit
  configuration and visible degradation evidence
- they are not guaranteed live in every environment

This page must not imply broad live provider deployment.

## 9. File-Level Change Boundary

Expected change surface:

- `backend/app/agent/graph.py`
- `backend/app/agent/retrieval_agent.py` if helper hooks are needed
- `backend/app/agent/extraction_agent.py` if helper hooks are needed
- `backend/app/agent/nodes.py` or a new helper module for runtime-summary
  derivation
- `backend/app/core/config.py`
- `backend/app/api/monitor.py` if response shaping needs adjustment
- `backend/app/templates/run_detail.html`
- `backend/app/templates/resume_alignment.html`
- `backend/README.md`
- tests in `backend/tests/test_tools_and_eval.py`
- tests in `backend/tests/test_monitor_run_flow.py`
- UI/API smoke tests if already present

Not in scope:

- new MCP providers
- Microsoft Playwright MCP-specific protocol support beyond the current HTTP
  compatibility contract
- React dashboard redesign
- distributed browser pools
- generic tool discovery UX

## 10. Test Strategy

The implementation must add or update tests in four groups.

### 10.1 Configuration And Summary Tests

Validate:

- settings can derive enabled versus disabled MCP/browser runtime summaries
- incomplete provider configuration produces truthful disabled summaries

### 10.2 Retrieval MCP Tests

Validate:

- a configured OneSearch gateway run marks MCP as enabled and used
- a failing OneSearch path marks MCP as enabled, used, and degraded to
  `mock_search`

### 10.3 Browser Fallback Tests

Validate:

- a configured Playwright fallback marks browser runtime as enabled
- browser fallback usage increments usage counters in the summary
- failed browser fallback increments failed-browser counters and preserves
  candidate failure state

### 10.4 End-To-End Run Tests

Validate:

- full run snapshots expose `integration_runtime`
- events and tool results remain consistent with the summary
- HTML pages render the summary without breaking existing surfaces

## 11. Acceptance Criteria

This slice is complete only when all of the following are true:

1. The repository has a stable per-run `integration_runtime` summary.
2. The summary truthfully distinguishes configuration from actual usage.
3. The summary truthfully distinguishes successful usage from degraded fallback.
4. MCP and browser-fallback evidence are visible through the run API and run
   detail HTML page.
5. README wording remains conservative and matches the implemented runtime.
6. No new provider or out-of-scope browsing capability is introduced.

## 12. Truth Boundary After This Slice

After implementation, the project may truthfully say:

- it has a real optional OneSearch-compatible MCP-backed search path
- it has a real optional Playwright MCP-compatible browser fallback path
- both paths expose explicit configuration, timeout/fallback behavior, and
  per-run runtime evidence

It still must not say:

- all environments run with live MCP or Playwright services
- the project manages a general MCP tool ecosystem
- browser automation is the default retrieval path
- the project operates a large-scale browser fleet
