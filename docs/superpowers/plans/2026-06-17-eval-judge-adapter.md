# Eval Judge Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a truthful LLM-as-Judge adapter boundary to eval results using a deterministic local judge implementation, without claiming live external model judging.

**Architecture:** Keep the existing rule scorer as the source of operational metrics. Add `app/eval/judge.py` with a protocol and `MockEvalJudge` that scores the already-computed metrics. Persist judge output in `eval_results` as structured fields and expose them through existing eval APIs.

**Tech Stack:** Python 3.12, Pydantic, SQLAlchemy JSON columns, pytest.

---

### Task 1: Add Judge Output Tests

**Files:**
- Modify: `backend/tests/test_tools_and_eval.py`
- Modify: `backend/tests/test_supporting_schema_contracts.py`

- [ ] **Step 1: Write a test for deterministic judge output**

Expected fields:

```text
judge_mode = "mock_rule_judge"
judge_score in [0.0, 1.0]
judge_reason is a non-empty string
judge_issues is a list of strings
```

- [ ] **Step 2: Write persistence/schema tests**

Repository and API schema should preserve judge fields in `EvalResultResponse`.

- [ ] **Step 3: Run the focused tests and verify they fail**

Run:

```powershell
cd backend
py -3.12 -m pytest tests/test_tools_and_eval.py::test_mock_eval_judge_scores_quality_metrics tests/test_tools_and_eval.py::test_sqlalchemy_repository_persists_eval_judge_fields tests/test_supporting_schema_contracts.py::test_eval_schema_accepts_judge_fields -q
```

Expected: FAIL because the judge module and fields do not exist.

### Task 2: Implement Judge Adapter And Persistence

**Files:**
- Create: `backend/app/eval/judge.py`
- Modify: `backend/app/storage/models.py`
- Modify: `backend/app/storage/repository.py`
- Modify: `backend/app/schemas/eval_schema.py`

- [ ] **Step 1: Add `MockEvalJudge`**

It accepts the rule score dict and returns:

```python
{
    "judge_mode": "mock_rule_judge",
    "judge_score": float,
    "judge_reason": str,
    "judge_issues": list[str],
}
```

Scoring rule: start at `1.0`, subtract `0.1` for duplicate pushes, subtract `0.15` if `fetch_success_rate < 1.0`, subtract `0.15` if `trace_completeness < 1.0`, clamp to `[0.0, 1.0]`.

- [ ] **Step 2: Add fields to eval persistence**

Add model columns and dataclass fields:

```text
judge_mode: str
judge_score: float
judge_reason: str
judge_issues: list[str]
```

- [ ] **Step 3: Expose fields through API schema**

Add the same fields to `EvalResultResponse`.

### Task 3: Integrate Judge Into The Monitor Graph

**Files:**
- Modify: `backend/app/agent/nodes.py`

- [ ] **Step 1: Apply judge during eval node**

After `score_run(state)`, call `MockEvalJudge().judge(eval_result)` and merge the returned fields into the eval result before persistence.

- [ ] **Step 2: Keep fallback truthful**

Name the mode `mock_rule_judge` so the code does not claim a live LLM judge.

### Task 4: Verify, Document, Commit

**Files:**
- Modify: `backend/README.md`

- [ ] **Step 1: Update README**

Move `LLM-as-Judge evaluation` from not claimed to included as `deterministic MockEvalJudge adapter for LLM-as-Judge contract`. Do not claim live external judge model support.

- [ ] **Step 2: Run verification**

Run:

```powershell
cd backend
py -3.12 -m pytest -q
py -3.12 -m compileall app
git diff --check
```

- [ ] **Step 3: Commit and push**

Run:

```powershell
git add backend/app/eval/judge.py backend/app/storage/models.py backend/app/storage/repository.py backend/app/schemas/eval_schema.py backend/app/agent/nodes.py backend/tests/test_tools_and_eval.py backend/tests/test_supporting_schema_contracts.py backend/README.md docs/superpowers/plans/2026-06-17-eval-judge-adapter.md
git commit -m "feat: add eval judge adapter"
git push
```

