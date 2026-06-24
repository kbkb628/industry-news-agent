# Structured RAG Grounding For Planner And Evaluation

**Goal:** Make the existing local RAG layer materially influence planner and evaluation behavior through a stable, truthful business-context contract.

**Scope:** This design covers only the current local `JSONL + retriever` path and its consumption inside `retrieve_business_context`, `PlannerAgent`, scoring, and evaluation explanation. It does not introduce a new external provider, vector database, or semantic history dedup flow.

**Why now:** The current project already retrieves local business context, but the retrieved knowledge is only partially consumed. Planner reads it loosely, while evaluation does not yet treat trusted-source guidance, push rules, and history guidance as first-class structured inputs. This leaves the repository weaker than the resume and development-guide wording around RAG-enhanced planning and decisioning.

---

## 1. Current State

The runtime already has a truthful local RAG path:

- `retrieve_business_context_node(...)` loads `knowledge_base.jsonl`
- `retrieve_hybrid_context(...)` returns hybrid retrieval evidence
- the result is persisted into `state["business_context"]`
- `PlannerAgent` reads `business_memory.business_context`

Current limitations:

- `business_context` is primarily a raw retrieval result, not a stable business-semantic contract
- planner uses context only indirectly and cannot clearly explain which knowledge guidance changed planning
- evaluation and score computation do not yet consume RAG guidance as structured scoring inputs
- run output cannot clearly prove that RAG changed push scoring or decision explanation

This design fixes those gaps without overstating the implementation boundary.

## 2. Design Principles

The implementation must preserve these rules:

1. Keep the current local RAG path truthful.
2. Do not describe this as external embedding RAG or production vector retrieval.
3. Preserve raw retrieval evidence for traceability.
4. Add a stable semantic layer that planner and evaluation can consume directly.
5. Limit this slice to `planner + evaluation`.
6. Do not expand this slice into semantic history dedup or provider integration work.

## 3. Target Business Context Contract

`business_context` should become a two-layer structure:

1. Raw evidence layer
2. Structured semantic-memory layer

Target shape:

```json
{
  "query": "AI Agent OpenAI enterprise automation",
  "retrieval_mode": "hybrid_keyword_bm25_embedding_rerank",
  "retrievers": ["keyword", "bm25", "embedding_like"],
  "documents": [
    {
      "doc_id": "kb_trusted_sources",
      "title": "Trusted sources improve push quality",
      "content": "Prefer trusted source domains when ranking industry news candidates because source quality reduces noisy pushes.",
      "keywords": ["trusted", "source", "quality", "ranking"],
      "score": 3.0,
      "rerank_score": 1.7,
      "retrievers": ["keyword", "bm25"],
      "scores": {
        "keyword": 2.0,
        "bm25": 1.0
      },
      "metadata": {
        "section": "guidance"
      }
    }
  ],
  "semantic_memory": {
    "topic_keywords": ["AI Agent", "MCP", "LangGraph"],
    "trusted_source_hints": ["langchain.com", "openai.com", "github.com"],
    "source_preferences": ["rss_first", "trusted_domain_priority"],
    "push_rules": [
      "prefer trusted source domains when scores are close",
      "penalize weak evidence or noisy summaries"
    ],
    "history_guidance": [
      "avoid repeating already-pushed angles within cooldown"
    ],
    "evidence_summary": [
      "knowledge base matched trusted-source guidance",
      "knowledge base matched candidate-scoring guidance"
    ]
  }
}
```

Contract requirements:

- `documents` remains the raw retrieval evidence surface
- `semantic_memory` is the stable planner/evaluation consumption surface
- empty retrieval must still return a predictable `semantic_memory` object with empty arrays
- document `metadata` must be preserved in retrieval output
- no existing caller should lose access to `documents`

## 4. Semantic-Memory Extraction Rules

`semantic_memory` should be derived deterministically from retrieved knowledge documents plus existing topic/business inputs.

### 4.1 Topic keywords

Sources:

- knowledge-document keywords
- document metadata tags when available
- existing topic seed keywords as fallback support

Rules:

- normalize and deduplicate case-insensitively
- keep only short topical terms, not full prose sentences
- preserve stable output ordering

### 4.2 Trusted source hints

Sources:

- document metadata trusted source domains
- existing topic trusted sources
- future knowledge entries that explicitly enumerate trusted domains

Rules:

- normalize domains case-insensitively
- merge topic-configured trusted sources with knowledge-derived trusted sources
- treat this as guidance for scoring and source planning, not as a hard allowlist

### 4.3 Source preferences

Sources:

- knowledge guidance about feed-first or trusted-domain-first retrieval
- local default retrieval policy already embodied by the project

Rules:

- keep the vocabulary intentionally small and explicit
- initial supported values should stay limited to patterns already real in the repo, such as `rss_first`, `search_first_if_context_sparse`, and `trusted_domain_priority`

### 4.4 Push rules

Sources:

- knowledge guidance related to source quality, evidence quality, and noise control

Rules:

- preserve concise human-readable rule text
- rules are explanatory guidance, not arbitrary executable expressions
- scoring code must map these strings into deterministic scoring effects rather than evaluating free-form logic

### 4.5 History guidance

Sources:

- knowledge guidance about novelty and repeated push avoidance
- existing push-history usage patterns

Rules:

- this slice does not build semantic history dedup
- this slice only clarifies how existing push history should influence scoring and explanation

## 5. Planner Behavior Changes

Planner enhancement must remain inside current system truth boundaries.

### 5.1 Query expansion input

`PlannerAgent` should continue to use `MockLLM.expand_keywords(...)`, but the expanded query set should be informed by both:

- topic seed keywords
- `semantic_memory.topic_keywords`

Result:

- query expansion becomes more grounded in retrieved domain vocabulary
- the system can truthfully claim that local RAG influences retrieval planning

### 5.2 Source planning

`build_structured_source_plan(...)` should consume:

- `semantic_memory.trusted_source_hints`
- `semantic_memory.source_preferences`
- existing topic trusted sources
- push-history count

Result:

- source order and reasons become explicitly tied to trusted-source memory and retrieval guidance
- planner explanations become more defensible and interview-safe

### 5.3 Planning reasons

`planning_reasons` should mention real guidance hits, for example:

- how many business-context documents were used
- whether trusted-source bias was applied
- whether knowledge guidance favored feed-first planning
- whether history context widened or constrained planning

This must remain deterministic and human-readable.

## 6. Evaluation Behavior Changes

Evaluation is the main gap this slice closes.

### 6.1 Structured scoring input

The scoring path should accept either:

- `business_context`
- or the narrower `semantic_memory`

Recommended implementation shape:

- `EvaluationAgent` extracts `semantic_memory`
- it passes that into `score_candidate`

The score tool should consume:

- `trusted_source_hints`
- `push_rules`
- `history_guidance`

### 6.2 Trusted-source weighting

When a candidate source matches `trusted_source_hints`, the score path may apply a bounded positive weight.

Rules:

- the weighting must be limited, not dominant
- a trusted source cannot rescue an otherwise weak or noisy candidate
- a non-trusted source must still remain eligible if topic relevance and evidence quality are strong

### 6.3 Guidance-based explanation

The score output and final decision explanation should include concise guidance traces such as:

- `matched trusted-source guidance`
- `applied weak-evidence penalty guidance`
- `history guidance suggests novelty caution`

These traces must be deterministic and generated by rule logic, not hallucinated model prose.

### 6.4 Eval metrics

`eval_result` should add a small RAG-impact surface so runs can prove the guidance was applied.

Candidate fields:

- `rag_guidance_applied_count`
- `trusted_source_match_count`
- `rule_guidance_hits`

These may initially live in the runtime state and API payload even if they are not yet added as separate relational columns.

## 7. State And Compatibility Strategy

Compatibility rules:

- keep `state["business_context"]` as the canonical business-context surface
- keep `state["business_memory"]["business_context"]` mirrored
- do not create a separate top-level `semantic_memory` field
- keep legacy output fields intact

This preserves current monitor APIs and dashboard assumptions while improving internal truthfulness.

## 8. File-Level Change Boundary

Expected change surface:

- `backend/app/rag/hybrid_retriever.py`
- `backend/app/rag/knowledge_loader.py` if metadata pass-through needs refinement
- `backend/app/rag/` new helper module for semantic-memory normalization
- `backend/app/agent/contracts.py`
- `backend/app/agent/nodes.py`
- `backend/app/agent/planner.py`
- `backend/app/agent/planner_agent.py`
- `backend/app/tools/scoring_tool.py`
- `backend/app/agent/evaluation_agent.py`
- `backend/app/eval/rule_scorer.py`
- `backend/app/rag/knowledge_base.jsonl`
- tests in `backend/tests/test_tools_and_eval.py`
- tests in `backend/tests/test_monitor_run_flow.py`

Not in scope:

- database schema redesign
- history-index provider changes
- OpenSearch-backed retrieval
- true embedding provider integration
- React feature expansion

## 9. Test Strategy

The implementation must add or update tests in four groups.

### 9.1 Retrieval-contract tests

Validate:

- `retrieve_hybrid_context(...)` returns `documents` plus `semantic_memory`
- document metadata survives retrieval
- empty or sparse retrieval still returns stable empty semantic-memory collections

### 9.2 Planner tests

Validate:

- planner query expansion incorporates semantic-memory topic keywords
- source plan reflects trusted-source and source-preference guidance
- planning reasons mention applied business-context guidance

### 9.3 Scoring and evaluation tests

Validate:

- trusted-source hints produce bounded positive weighting
- push-rule guidance affects scoring/explanation deterministically
- evaluation output and final decisions expose guidance-based reasoning without replacing existing cooldown or duplicate logic

### 9.4 End-to-end run tests

Validate:

- a full run stores `business_context.semantic_memory`
- planner output changes based on retrieved business context
- evaluation output and `eval_result` show RAG-guidance usage
- candidate orchestration and existing API compatibility do not regress

## 10. Acceptance Criteria

This slice is complete only when all of the following are true:

1. The codebase can point to a stable `semantic_memory` contract inside `business_context`.
2. Planner behavior demonstrably changes based on that contract.
3. Evaluation/scoring behavior demonstrably changes based on that contract.
4. Run state and user-visible outputs can show RAG guidance influence.
5. No external provider is required to run the feature.
6. Existing monitor graph, candidate orchestration, and API compatibility remain intact.

## 11. Truth Boundary After This Slice

After implementation, the project may truthfully say:

- local business knowledge retrieval grounds query planning
- trusted-source and rule guidance influence scoring and decision explanation
- RAG is used for topic vocabulary, source trust, push guidance, and history guidance

It still must not say:

- production vector RAG is deployed
- semantic history dedup is fully implemented
- external MCP/OpenSearch retrieval is required for this capability

## 12. Out Of Scope Follow-Ups

These remain later-phase work:

- semantic history dedup backed by embeddings or OpenSearch
- provider-backed retrievers
- history-index retrieval folded directly into planner or evaluation
- LLM-as-Judge consuming RAG evidence directly
- richer dashboard visualization for RAG evidence
