# OpenAI-Compatible Eval Judge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional OpenAI-compatible eval judge provider while preserving deterministic MockEvalJudge fallback and truthful capability boundaries.

**Architecture:** `MockEvalJudge` remains the default. `OpenAICompatibleEvalJudge` posts the rule metrics to an OpenAI-compatible chat completions endpoint and parses a strict JSON response into the existing judge fields. `build_eval_judge(settings, http_client)` chooses provider by config and falls back explicitly to mock when provider config is incomplete or calls fail.

**Tech Stack:** Python 3.12, pydantic-settings, httpx-compatible client injection, pytest.

---

### Task 1: Add Provider Contract Tests

**Files:**
- Modify: `backend/tests/test_tools_and_eval.py`
- Modify: `backend/app/core/config.py`

- [ ] **Step 1: Write tests for settings fields**

Expected config fields:

```text
judge_provider
judge_base_url
judge_api_key
judge_model
judge_timeout_seconds
```

- [ ] **Step 2: Write tests for OpenAI-compatible judge**

Use a fake HTTP client with `post()` returning a response whose JSON contains:

```json
{"choices":[{"message":{"content":"{\"judge_score\":0.82,\"judge_reason\":\"Useful.\",\"judge_issues\":[\"trace_incomplete\"]}"}}]}
```

Expected result:

```text
judge_mode = openai_compatible_judge
judge_score = 0.82
judge_reason = Useful.
judge_issues = ["trace_incomplete"]
```

- [ ] **Step 3: Write fallback test**

When provider is `openai_compatible` but HTTP call raises, `FallbackEvalJudge` must return mock judge fields plus:

```text
judge_mode = mock_rule_judge
judge_issues contains judge_provider_fallback
```

### Task 2: Implement Provider And Builder

**Files:**
- Modify: `backend/app/eval/judge.py`
- Modify: `backend/app/core/config.py`

- [ ] **Step 1: Add settings**

Defaults:

```text
judge_provider = mock
judge_base_url = None
judge_api_key = None
judge_model = gpt-4o-mini
judge_timeout_seconds = 10.0
```

- [ ] **Step 2: Add `OpenAICompatibleEvalJudge`**

Constructor accepts `base_url`, `api_key`, `model`, `timeout_seconds`, and optional `http_client`.

- [ ] **Step 3: Add `build_eval_judge`**

Return mock unless provider is `openai_compatible` and both base URL and API key are set. Wrap external judge in `FallbackEvalJudge`.

### Task 3: Integrate Runtime

**Files:**
- Modify: `backend/app/agent/nodes.py`
- Modify: `backend/README.md`

- [ ] **Step 1: Use builder in eval node**

Use `_get_optional_settings()` and `build_eval_judge(settings)` so runtime can switch provider by environment.

- [ ] **Step 2: Document configuration**

README must state that live external judge calls require explicit `JUDGE_PROVIDER=openai_compatible`, `JUDGE_BASE_URL`, and `JUDGE_API_KEY`.

### Task 4: Verify And Commit

- [ ] **Step 1: Run focused tests**

```powershell
cd backend
py -3.12 -m pytest tests/test_tools_and_eval.py::test_settings_accept_eval_judge_provider_values tests/test_tools_and_eval.py::test_openai_compatible_eval_judge_parses_json_response tests/test_tools_and_eval.py::test_eval_judge_builder_falls_back_to_mock_when_provider_fails -q
```

- [ ] **Step 2: Run full verification**

```powershell
py -3.12 -m pytest -q
py -3.12 -m compileall app
git diff --check
```

- [ ] **Step 3: Commit and push**

```powershell
git add backend/app/eval/judge.py backend/app/core/config.py backend/app/agent/nodes.py backend/tests/test_tools_and_eval.py backend/README.md docs/superpowers/plans/2026-06-17-openai-compatible-eval-judge.md
git commit -m "feat: add openai compatible eval judge"
git push
```

