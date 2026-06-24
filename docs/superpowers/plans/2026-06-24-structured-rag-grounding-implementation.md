# Structured RAG Grounding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing local RAG layer materially affect planner behavior and evaluation/scoring behavior through a stable `business_context.semantic_memory` contract.

**Architecture:** Keep the current local `JSONL + hybrid retriever` design, but normalize retrieved knowledge into a structured semantic-memory layer that sits alongside raw retrieval evidence. Planner consumes this layer for query/source planning, and evaluation/scoring consumes it for trusted-source weighting, rule guidance, and decision explanation, while preserving current monitor graph and compatibility fields.

**Tech Stack:** Python 3.12, FastAPI backend, LangGraph state flow, local JSONL knowledge base, Pydantic-style typed contracts, pytest

---

### Task 1: Add Structured Semantic-Memory Output To Local RAG

**Files:**
- Create: `backend/app/rag/semantic_memory.py`
- Modify: `backend/app/rag/hybrid_retriever.py`
- Modify: `backend/app/rag/knowledge_base.jsonl`
- Test: `backend/tests/test_tools_and_eval.py`

- [ ] **Step 1: Write the failing retrieval-contract tests**

Add tests to `backend/tests/test_tools_and_eval.py` that assert:

```python
def test_retrieve_hybrid_context_returns_semantic_memory() -> None:
    documents = [
        KnowledgeDocument(
            doc_id="kb_trusted_sources",
            title="Trusted sources improve push quality",
            content="Prefer trusted source domains when ranking industry news candidates because source quality reduces noisy pushes.",
            keywords=["trusted", "source", "quality", "ranking"],
            metadata={
                "section": "guidance",
                "trusted_sources": ["openai.com", "github.com"],
                "topic_keywords": ["AI Agent", "MCP"],
                "source_preferences": ["rss_first", "trusted_domain_priority"],
                "push_rules": ["prefer trusted source domains when scores are close"],
                "history_guidance": ["avoid repeating already-pushed angles within cooldown"],
            },
        )
    ]

    context = retrieve_hybrid_context(documents, "AI Agent MCP", top_k=3)

    assert context["documents"][0]["metadata"]["trusted_sources"] == ["openai.com", "github.com"]
    assert context["semantic_memory"]["topic_keywords"] == ["AI Agent", "MCP"]
    assert context["semantic_memory"]["trusted_source_hints"] == ["openai.com", "github.com"]
    assert context["semantic_memory"]["source_preferences"] == [
        "rss_first",
        "trusted_domain_priority",
    ]
    assert context["semantic_memory"]["push_rules"] == [
        "prefer trusted source domains when scores are close"
    ]
    assert context["semantic_memory"]["history_guidance"] == [
        "avoid repeating already-pushed angles within cooldown"
    ]
    assert context["semantic_memory"]["evidence_summary"]


def test_retrieve_hybrid_context_returns_empty_semantic_memory_when_no_documents_match() -> None:
    documents = [
        KnowledgeDocument(
            doc_id="kb_other_topic",
            title="Browser fallback should stay last",
            content="Use browser fallback only after RSS and HTTP fail.",
            keywords=["browser", "fallback"],
            metadata={"section": "guidance"},
        )
    ]

    context = retrieve_hybrid_context(documents, "pharma policy", top_k=3)

    assert context["documents"] == []
    assert context["semantic_memory"] == {
        "topic_keywords": [],
        "trusted_source_hints": [],
        "source_preferences": [],
        "push_rules": [],
        "history_guidance": [],
        "evidence_summary": [],
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.12 -m pytest backend/tests/test_tools_and_eval.py -q -k "semantic_memory"`

Expected: FAIL because `retrieve_hybrid_context(...)` does not yet return `semantic_memory`, and raw document metadata is not fully passed through.

- [ ] **Step 3: Add the semantic-memory normalizer and wire it into hybrid retrieval**

Create `backend/app/rag/semantic_memory.py`:

```python
from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def _dedupe(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value).strip()
        lowered = normalized.lower()
        if not normalized or lowered in seen:
            continue
        seen.add(lowered)
        result.append(normalized)
    return result


def build_empty_semantic_memory() -> dict[str, list[str]]:
    return {
        "topic_keywords": [],
        "trusted_source_hints": [],
        "source_preferences": [],
        "push_rules": [],
        "history_guidance": [],
        "evidence_summary": [],
    }


def build_semantic_memory(documents: list[dict[str, Any]]) -> dict[str, list[str]]:
    if not documents:
        return build_empty_semantic_memory()

    topic_keywords: list[str] = []
    trusted_source_hints: list[str] = []
    source_preferences: list[str] = []
    push_rules: list[str] = []
    history_guidance: list[str] = []
    evidence_summary: list[str] = []

    for document in documents:
        metadata = dict(document.get("metadata", {}))
        topic_keywords.extend(str(item) for item in metadata.get("topic_keywords", []))
        trusted_source_hints.extend(str(item) for item in metadata.get("trusted_sources", []))
        source_preferences.extend(str(item) for item in metadata.get("source_preferences", []))
        push_rules.extend(str(item) for item in metadata.get("push_rules", []))
        history_guidance.extend(str(item) for item in metadata.get("history_guidance", []))

        title = str(document.get("title", "")).strip()
        if title:
            evidence_summary.append(f"knowledge base matched {title.lower()}")

    return {
        "topic_keywords": _dedupe(topic_keywords),
        "trusted_source_hints": _dedupe(trusted_source_hints),
        "source_preferences": _dedupe(source_preferences),
        "push_rules": _dedupe(push_rules),
        "history_guidance": _dedupe(history_guidance),
        "evidence_summary": _dedupe(evidence_summary),
    }
```

Update `backend/app/rag/hybrid_retriever.py` to:

```python
from app.rag.semantic_memory import build_semantic_memory
```

and change the return shape so each document includes `metadata`:

```python
documents_payload = [
    {
        "doc_id": item["document"].doc_id,
        "title": item["document"].title,
        "content": item["document"].content,
        "keywords": list(item["document"].keywords),
        "score": item["score"],
        "rerank_score": item["rerank_score"],
        "retrievers": list(item["retrievers"]),
        "scores": dict(item["scores"]),
        "metadata": dict(item["document"].metadata),
    }
    for item in ranked_hits
]

return {
    "query": query,
    "retrieval_mode": RETRIEVAL_MODE,
    "retrievers": list(RETRIEVERS),
    "documents": documents_payload,
    "semantic_memory": build_semantic_memory(documents_payload),
}
```

Update `backend/app/rag/knowledge_base.jsonl` by expanding guidance metadata, for example:

```json
{"doc_id":"kb_trusted_sources","title":"trusted-source guidance","content":"Prefer trusted source domains when ranking industry news candidates because source quality reduces noisy pushes.","keywords":["trusted","source","quality","ranking"],"metadata":{"section":"guidance","trusted_sources":["openai.com","github.com","langchain.com"],"topic_keywords":["AI Agent","MCP","LangGraph"],"source_preferences":["rss_first","trusted_domain_priority"],"push_rules":["prefer trusted source domains when scores are close"]}}
{"doc_id":"kb_candidate_scoring","title":"candidate-scoring guidance","content":"Score candidates by topic relevance, evidence quality, and trusted source alignment before pushing a summary.","keywords":["scoring","relevance","trusted","source"],"metadata":{"section":"guidance","push_rules":["penalize weak evidence or noisy summaries"],"history_guidance":["avoid repeating already-pushed angles within cooldown"]}}
{"doc_id":"kb_article_extraction","title":"article-extraction guidance","content":"Extract a concise article summary and stable keywords so later steps can evaluate the candidate consistently.","keywords":["summary","keywords","extraction"],"metadata":{"section":"guidance","topic_keywords":["structured extraction","stable keywords"]}}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.12 -m pytest backend/tests/test_tools_and_eval.py -q -k "semantic_memory"`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/rag/semantic_memory.py backend/app/rag/hybrid_retriever.py backend/app/rag/knowledge_base.jsonl backend/tests/test_tools_and_eval.py
git commit -m "feat: add structured semantic memory to local rag"
```

### Task 2: Make Planner Consume Semantic Memory For Queries, Sources, And Reasons

**Files:**
- Modify: `backend/app/agent/planner.py`
- Modify: `backend/app/agent/planner_agent.py`
- Modify: `backend/app/agent/contracts.py`
- Test: `backend/tests/test_tools_and_eval.py`
- Test: `backend/tests/test_monitor_run_flow.py`

- [ ] **Step 1: Write the failing planner tests**

Add tests that assert planner behavior changes when `semantic_memory` is present:

```python
def test_planner_agent_merges_semantic_memory_topic_keywords_into_expanded_queries() -> None:
    planner = PlannerAgent(llm=MockLLM())
    state = {
        "topic": {
            "topic_id": "topic_ai",
            "name": "AI Agent",
            "trusted_sources": ["openai.com"],
        },
        "business_memory": {
            "seed_keywords": ["OpenAI", "enterprise"],
            "trusted_sources": ["openai.com"],
            "push_history": [],
            "business_context": {
                "documents": [],
                "semantic_memory": {
                    "topic_keywords": ["MCP", "LangGraph"],
                    "trusted_source_hints": ["github.com"],
                    "source_preferences": ["rss_first", "trusted_domain_priority"],
                    "push_rules": [],
                    "history_guidance": [],
                    "evidence_summary": ["knowledge base matched trusted-source guidance"],
                },
            },
        },
        "planner_output": {},
        "expanded_queries": [],
        "source_plan": [],
    }

    result = planner.run(state)

    assert "MCP" in result["planner_output"]["expanded_queries"]
    assert "LangGraph" in result["planner_output"]["expanded_queries"]


def test_build_structured_source_plan_uses_semantic_memory_preferences_and_trusted_sources() -> None:
    source_plan = build_structured_source_plan(
        {
            "trusted_sources": ["openai.com"],
        },
        trusted_sources=["openai.com"],
        push_history=[],
        business_context={
            "documents": [{"doc_id": "kb_1"}],
            "semantic_memory": {
                "topic_keywords": [],
                "trusted_source_hints": ["github.com"],
                "source_preferences": ["rss_first", "trusted_domain_priority"],
                "push_rules": [],
                "history_guidance": [],
                "evidence_summary": [],
            },
        },
    )

    assert source_plan[0]["tool_name"] == "rss_fetch"
    assert "trusted" in source_plan[0]["reason"].lower()
    assert "github.com" in source_plan[0]["trusted_sources"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.12 -m pytest backend/tests/test_tools_and_eval.py backend/tests/test_monitor_run_flow.py -q -k "planner_agent_merges_semantic_memory or build_structured_source_plan_uses_semantic_memory"`

Expected: FAIL because planner does not yet merge `semantic_memory` into expanded queries or source planning.

- [ ] **Step 3: Update planner contract and planner logic**

Update `backend/app/agent/contracts.py` so `build_empty_business_memory()` seeds a structured default:

```python
        "business_context": {
            "documents": [],
            "semantic_memory": {
                "topic_keywords": [],
                "trusted_source_hints": [],
                "source_preferences": [],
                "push_rules": [],
                "history_guidance": [],
                "evidence_summary": [],
            },
        },
```

Update `backend/app/agent/planner.py`:

- add a helper:

```python
def _semantic_memory(context: dict[str, Any] | None) -> dict[str, Any]:
    return dict((context or {}).get("semantic_memory", {}))
```

- update `build_structured_source_plan(...)` to merge:

```python
semantic_memory = _semantic_memory(business_context)
semantic_trusted_sources = list(semantic_memory.get("trusted_source_hints", []))
combined_trusted_sources = _dedupe_strings(
    [*topic_trusted_sources, *trusted_sources, *semantic_trusted_sources]
)
source_preferences = {
    str(item).strip().lower()
    for item in semantic_memory.get("source_preferences", [])
    if str(item).strip()
}
prefer_rss = "rss_first" in source_preferences or "trusted_domain_priority" in source_preferences
search_priority = 2 if prefer_rss else 1
rss_priority = 1 if prefer_rss else 2
```

- update source reasons to mention semantic guidance explicitly

- update `build_planning_reasons(...)` so it includes evidence-summary and preference signals, for example:

```python
semantic_memory = _semantic_memory(business_context)
evidence_summary = list(semantic_memory.get("evidence_summary", []))
source_preferences = list(semantic_memory.get("source_preferences", []))
return [
    f"Topic '{topic_name}' requires recall across feed and search sources.",
    f"Loaded {document_count} business-context documents into planning.",
    f"Trusted source bias applied to {trusted_source_count} domains.",
    f"Considered {history_count} historical push records to avoid narrow planning.",
    f"Semantic memory contributed {len(evidence_summary)} guidance hit(s).",
    f"Semantic source preferences: {', '.join(source_preferences) or 'none'}.",
]
```

Update `backend/app/agent/planner_agent.py`:

```python
semantic_memory = dict(business_context.get("semantic_memory", {}))
semantic_topic_keywords = [
    str(item)
    for item in semantic_memory.get("topic_keywords", [])
]
if not expanded_queries:
    expanded_queries = self.llm.expand_keywords(
        topic_name=topic_name,
        seed_keywords=[*seed_keywords, *semantic_topic_keywords],
    )
else:
    expanded_queries = [*expanded_queries, *semantic_topic_keywords]
```

and then de-duplicate before building the query plan.

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.12 -m pytest backend/tests/test_tools_and_eval.py backend/tests/test_monitor_run_flow.py -q -k "planner_agent_merges_semantic_memory or build_structured_source_plan_uses_semantic_memory"`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/planner.py backend/app/agent/planner_agent.py backend/app/agent/contracts.py backend/tests/test_tools_and_eval.py backend/tests/test_monitor_run_flow.py
git commit -m "feat: ground planner with semantic memory"
```

### Task 3: Pass Semantic Memory Into Scoring And Evaluation Explanation

**Files:**
- Modify: `backend/app/tools/scoring_tool.py`
- Modify: `backend/app/agent/evaluation_agent.py`
- Modify: `backend/app/tools/registry.py`
- Test: `backend/tests/test_tools_and_eval.py`
- Test: `backend/tests/test_monitor_run_flow.py`

- [ ] **Step 1: Write the failing scoring/evaluation tests**

Add tests such as:

```python
def test_score_candidates_tool_uses_semantic_memory_for_trusted_source_and_guidance_breakdown() -> None:
    tool = ScoreCandidatesTool(llm=MockLLM())

    response = tool(
        topic={
            "name": "AI Agent",
            "seed_keywords": ["OpenAI"],
            "trusted_sources": ["tech.example.com"],
            "exclude_keywords": [],
        },
        articles=[
            {
                "candidate_id": "cand_001",
                "title": "OpenAI ships enterprise agent workflow",
                "summary": "Trusted-source launch details",
                "source_name": "openai.com",
                "keywords": ["AI Agent"],
            }
        ],
        business_context={
            "semantic_memory": {
                "topic_keywords": ["MCP"],
                "trusted_source_hints": ["openai.com"],
                "source_preferences": [],
                "push_rules": [
                    "prefer trusted source domains when scores are close",
                    "penalize weak evidence or noisy summaries",
                ],
                "history_guidance": ["avoid repeating already-pushed angles within cooldown"],
                "evidence_summary": [],
            }
        },
    )

    article = response.data["articles"][0]
    assert "semantic trusted source +0.10" in article["score_breakdown"]
    assert "guidance:" in article["score_breakdown"]


def test_evaluation_agent_produces_rag_guidance_metrics() -> None:
    gateway = LocalToolGateway()
    build_default_tool_registry(llm=MockLLM()).register_into(gateway)
    agent = EvaluationAgent(gateway=gateway, settings=None)
    state = {
        "run_id": "run_rag_eval",
        "topic_id": "topic_ai",
        "topic": {
            "topic_id": "topic_ai",
            "name": "AI Agent",
            "push_threshold": 0.7,
            "cooldown_hours": 24,
            "trusted_sources": ["openai.com"],
            "exclude_keywords": [],
            "seed_keywords": ["OpenAI"],
        },
        "business_memory": {
            "push_history": [],
            "business_context": {
                "documents": [],
                "semantic_memory": {
                    "topic_keywords": ["MCP"],
                    "trusted_source_hints": ["openai.com"],
                    "source_preferences": [],
                    "push_rules": ["prefer trusted source domains when scores are close"],
                    "history_guidance": ["avoid repeating already-pushed angles within cooldown"],
                    "evidence_summary": ["knowledge base matched trusted-source guidance"],
                },
            },
        },
        "extraction_output": {
            "evidence_items": [
                {
                    "candidate_id": "cand_001",
                    "title": "OpenAI ships enterprise agent workflow",
                    "summary": "Strong evidence for enterprise launch",
                    "source_type": "search",
                    "source_name": "openai.com",
                    "url": "https://openai.com/news/agents",
                }
            ]
        },
        "evaluation_output": {},
        "tool_results": [],
        "errors": [],
        "events": [],
    }

    result = agent.run(state)

    assert result["eval_result"]["rag_guidance_applied_count"] >= 1
    assert result["eval_result"]["trusted_source_match_count"] == 1
    assert result["eval_result"]["rule_guidance_hits"] >= 1
    assert "trusted source" in result["final_decisions"][0]["decision_reason"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.12 -m pytest backend/tests/test_tools_and_eval.py backend/tests/test_monitor_run_flow.py -q -k "semantic_memory_for_trusted_source or rag_guidance_metrics"`

Expected: FAIL because `score_candidate` does not accept `business_context`, and `eval_result` does not yet expose RAG-impact metrics.

- [ ] **Step 3: Update scoring tool, registry contract, and evaluation agent**

Update `backend/app/tools/scoring_tool.py` so the tool signature becomes:

```python
def __call__(
    self,
    *,
    topic: dict[str, Any],
    articles: list[dict[str, Any]],
    business_context: dict[str, Any] | None = None,
) -> object:
```

and add:

```python
semantic_memory = dict((business_context or {}).get("semantic_memory", {}))
semantic_trusted_sources = {
    str(source).lower()
    for source in semantic_memory.get("trusted_source_hints", [])
}
push_rules = [str(item) for item in semantic_memory.get("push_rules", [])]
history_guidance = [str(item) for item in semantic_memory.get("history_guidance", [])]
```

Then apply bounded scoring and explanation:

```python
if source_name in semantic_trusted_sources:
    score += 0.10
    breakdown_parts.append("semantic trusted source +0.10")

guidance_hits: list[str] = []
if push_rules:
    guidance_hits.append("push_rules")
if history_guidance:
    guidance_hits.append("history_guidance")
if guidance_hits:
    breakdown_parts.append(f"guidance: {', '.join(guidance_hits)}")

scored_article["rag_guidance_hits"] = guidance_hits
scored_article["trusted_source_match"] = source_name in semantic_trusted_sources
```

Update `backend/app/agent/evaluation_agent.py`:

- read `business_context` from `business_memory`
- pass it into `score_candidate`

```python
business_context = dict(
    state.get("business_memory", {}).get(
        "business_context",
        state.get("business_context", {}),
    )
)
```

and:

```python
score_response = _call_tool(
    state,
    self.gateway,
    "score_candidate",
    topic=topic,
    articles=deduped_items,
    business_context=business_context,
)
```

After decisions are produced, compute lightweight guidance metrics and fold them into `eval_result`:

```python
rag_guidance_applied_count = sum(
    1 for item in scored_items if item.get("rag_guidance_hits")
)
trusted_source_match_count = sum(
    1 for item in scored_items if item.get("trusted_source_match") is True
)
rule_guidance_hits = sum(
    len(item.get("rag_guidance_hits", [])) for item in scored_items
)
eval_result = score_run(state)
eval_result.update(
    {
        "rag_guidance_applied_count": rag_guidance_applied_count,
        "trusted_source_match_count": trusted_source_match_count,
        "rule_guidance_hits": rule_guidance_hits,
    }
)
```

Keep these values in runtime/API state only for this slice; do not add new relational columns.

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.12 -m pytest backend/tests/test_tools_and_eval.py backend/tests/test_monitor_run_flow.py -q -k "semantic_memory_for_trusted_source or rag_guidance_metrics"`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/tools/scoring_tool.py backend/app/agent/evaluation_agent.py backend/app/tools/registry.py backend/tests/test_tools_and_eval.py backend/tests/test_monitor_run_flow.py
git commit -m "feat: ground evaluation with semantic memory"
```

### Task 4: Verify End-To-End Compatibility And Finalize The Slice

**Files:**
- Modify: `PROJECT_TODO.md`
- Test: `backend/tests/test_tools_and_eval.py`
- Test: `backend/tests/test_monitor_run_flow.py`
- Test: `backend/tests/test_health_api.py`
- Test: `backend/tests/test_topics_api.py`

- [ ] **Step 1: Add the end-to-end regression assertions**

Extend an existing monitor graph test in `backend/tests/test_monitor_run_flow.py` so it asserts:

```python
assert "semantic_memory" in result["business_context"]
assert isinstance(result["business_context"]["semantic_memory"]["topic_keywords"], list)
assert result["planner_output"]["planning_reasons"]
assert "Semantic memory contributed" in " ".join(result["planner_output"]["planning_reasons"])
assert "rag_guidance_applied_count" in result["eval_result"]
assert "trusted_source_match_count" in result["eval_result"]
assert "rule_guidance_hits" in result["eval_result"]
```

- [ ] **Step 2: Run focused backend regression tests**

Run: `py -3.12 -m pytest backend/tests/test_tools_and_eval.py backend/tests/test_monitor_run_flow.py backend/tests/test_topics_api.py backend/tests/test_health_api.py -q`

Expected: PASS

- [ ] **Step 3: Run full backend test suite**

Run: `py -3.12 -m pytest backend -q`

Expected: PASS

- [ ] **Step 4: Update milestone tracking**

Update `PROJECT_TODO.md` so:

- `implement structured RAG grounding for planner and evaluation` moves to `completed`
- `spec and planning for structured RAG grounding` moves to `completed`
- no stale `in_progress` item remains for this slice

- [ ] **Step 5: Commit**

```bash
git add PROJECT_TODO.md backend/tests/test_tools_and_eval.py backend/tests/test_monitor_run_flow.py
git commit -m "feat: complete structured rag grounding slice"
```

## Self-Review

### Spec coverage

- `business_context.semantic_memory` contract is implemented in Task 1.
- planner query/source/reason grounding is implemented in Task 2.
- evaluation/scoring grounding is implemented in Task 3.
- end-to-end evidence and milestone closure are implemented in Task 4.

### Placeholder scan

- No `TBD`, `TODO`, or “implement later” placeholders are present in tasks.
- Every task includes exact files, code targets, and test commands.

### Type consistency

- The plan uses one stable contract name: `business_context.semantic_memory`.
- Planner and evaluation both consume the same semantic-memory keys:
  `topic_keywords`, `trusted_source_hints`, `source_preferences`,
  `push_rules`, `history_guidance`, `evidence_summary`.
