import "@testing-library/jest-dom/vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const respond = (body: unknown, ok = true) =>
  Promise.resolve({
    ok,
    status: ok ? 200 : 404,
    json: () => Promise.resolve(body),
  } as Response);

describe("App", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockImplementation((path: string) => {
      if (path === "/api/topics") {
        return respond([
          {
            topic_id: "topic_001",
            name: "AI Agent",
            description: "Track agent launches",
            seed_keywords: ["AI Agent", "MCP"],
            trusted_sources: ["github.com"],
            exclude_keywords: [],
            push_threshold: 0.72,
            cooldown_hours: 24,
            enabled: true,
            schedule_cron: "0 */6 * * *",
          },
        ]);
      }
      if (path === "/api/pushes") {
        return respond({
          pushes: [
            {
              push_id: "push_001",
              run_id: "run_001",
              topic_id: "topic_001",
              candidate_id: "cand_001",
              should_push: true,
              score: 0.91,
              decision_reason: "High value",
            },
          ],
        });
      }
      if (path === "/api/eval/summary") {
        return respond({
          run_count: 3,
          total_push_count: 1,
          total_duplicate_push_count: 0,
          total_raw_summary_count: 0,
          total_browser_fallback_count: 1,
          total_provider_fallback_count: 1,
          total_false_positive_proxy_count: 1,
          avg_tool_success_rate: 1,
          avg_fetch_success_rate: 0.75,
          avg_trace_completeness: 0.9,
          avg_candidate_recall_proxy: 0.82,
          avg_candidate_task_failure_rate: 0.11,
          avg_event_latency_ms: 245,
          latest_eval: {
            eval_id: "eval_001",
            run_id: "run_001",
            topic_id: "topic_001",
            retrieved_count: 4,
            deduped_count: 3,
            push_count: 1,
            tool_success_rate: 1,
            candidate_recall_proxy: 0.82,
            false_positive_proxy_count: 1,
            candidate_task_failure_rate: 0.11,
            avg_event_latency_ms: 245,
            runtime_cost_proxy: {
              tool_calls: 5,
              browser_fallbacks: 1,
              model_decisions: 2,
            },
          },
        });
      }
      if (path === "/api/monitor/runs/run_001") {
        return respond({
          run_id: "run_001",
          topic_id: "topic_001",
          trigger: "manual",
          status: "completed",
          run_context: {
            trigger_source: "dashboard",
            requested_by: "demo_operator",
          },
          business_memory: {
            push_history: [{ title: "Prior agent funding alert" }],
            documents: [{ doc_id: "kb_001", title: "Trusted sources improve push quality" }],
            business_context: {
              retrieval_mode: "hybrid",
              retrievers: ["keyword", "bm25", "embedding"],
              semantic_memory: {
                topic_keywords: ["AI Agent", "MCP"],
                trusted_source_hints: ["openai.com", "github.com"],
                source_preferences: ["rss_first", "trusted_domain_priority"],
                push_rules: [
                  "prefer trusted source domains when scores are close",
                ],
              },
            },
          },
          expanded_queries: ["AI Agent funding"],
          candidate_items: [{ title: "Agent launch" }],
          final_decisions: [{ title: "Agent launch", should_push: true }],
          planner_output: {
            expanded_queries: ["AI Agent funding"],
            source_plan: [
              { tool_name: "rss_fetch", priority: 1 },
              { tool_name: "search_news", priority: 2 },
            ],
            planning_reasons: [
              "Trusted-source guidance favored feed-first planning.",
            ],
          },
          retrieval_output: {
            candidate_pool: [{ candidate_id: "cand_001", title: "Agent launch" }],
            provider_fallbacks: [],
          },
          extraction_output: {
            fetched_contents: [{ candidate_id: "cand_001", content: "full article" }],
            evidence_items: [{ extracted_id: "ext_001", title: "Agent launch" }],
          },
          evaluation_output: {
            final_decisions: [{ title: "Agent launch", should_push: true }],
            push_records: [{ push_id: "push_001", should_push: true }],
            eval_result: {
              rag_guidance_applied_count: 1,
              trusted_source_match_count: 1,
              rule_guidance_hits: 2,
            },
          },
          history_index_result: {
            provider: "opensearch",
            indexed_count: 2,
            search: {
              query: "OpenAI agent",
              returned_count: 1,
              items: [{ candidate_id: "cand_hist_001", title: "OpenAI agent update" }],
            },
          },
          integration_runtime: {
            mcp: {
              configured_provider: "onesearch",
              enabled: true,
              used_in_run: false,
              fallback_used: true,
            },
            browser: {
              configured_provider: "playwright_mcp",
              enabled: true,
              used_in_run: true,
              fallback_used: true,
              allowed_domains: ["example.com"],
            },
            notification: {
              configured_provider: "webhook",
              enabled: true,
              used_in_run: true,
              delivery_succeeded: true,
            },
            tool_access: {
              contract: "unified_tool_gateway",
              search: {
                provider_path: "mcp_gateway",
                tool_name: "search_news",
              },
              browser: {
                provider_path: "tool_gateway",
                tool_name: "fetch_article_content",
              },
              notification: {
                provider_path: "tool_gateway",
                tool_name: "notification_send",
              },
            },
          },
          candidate_task_summary: {
            task_count: 3,
            completed_count: 3,
            skipped_count: 0,
            failed_count: 0,
            fetch_completed_count: 1,
            extract_completed_count: 1,
            evaluate_completed_count: 1,
          },
          errors: [],
        });
      }
      if (path === "/api/monitor/runs/run_001/events") {
        return respond({
          run_id: "run_001",
          events: [
            {
              event_id: "evt_001",
              run_id: "run_001",
              topic_id: "topic_001",
              event_type: "node_completed",
              node: "retrieve_candidates",
              message: "Retrieved candidate items.",
              payload: { count: 1 },
            },
          ],
        });
      }
      if (path === "/api/monitor/runs/run_001/candidate-tasks") {
        return respond({
          items: [
            {
              task_id: "task_fetch_001",
              run_id: "run_001",
              stage: "fetch",
              status: "completed",
              candidate_id: "cand_001",
              attempt: 1,
              max_attempts: 2,
              output_ref: { extracted_id: "ext_001" },
            },
            {
              task_id: "task_extract_001",
              run_id: "run_001",
              stage: "extract",
              status: "completed",
              candidate_id: "cand_001",
              attempt: 1,
              max_attempts: 2,
              depends_on_task_ids: ["task_fetch_001"],
              output_ref: { extracted_id: "ext_001" },
            },
            {
              task_id: "task_evaluate_001",
              run_id: "run_001",
              stage: "evaluate",
              status: "completed",
              candidate_id: "cand_001",
              attempt: 2,
              max_attempts: 2,
              depends_on_task_ids: ["task_extract_001"],
              output_ref: { decision_id: "dec_001" },
            },
          ],
        });
      }
      return respond({ detail: "not found" }, false);
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    fetchMock.mockReset();
  });

  it("renders dashboard summary, topics, pushes, and quality metrics", async () => {
    render(<App />);

    expect(
      await screen.findByRole("heading", { name: /Industry News Agent/i }),
    ).toBeInTheDocument();
    expect(
      await screen.findByText(
        /Supervisor -> Planner -> Retrieval -> CandidateTaskOrchestrator -> Finalize/i,
      ),
    ).toBeInTheDocument();
    expect(
      await screen.findByText(/Quality and fallback signals/i),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("heading", {
        name: /APScheduler, queue, worker, retry, active-run guard/i,
      }),
    ).toBeInTheDocument();
    expect(await screen.findByText("AI Agent")).toBeInTheDocument();
    expect(await screen.findByText("push_001")).toBeInTheDocument();
    expect(await screen.findByText("Tool success")).toBeInTheDocument();
    expect(await screen.findByText("100%")).toBeInTheDocument();
    expect(await screen.findByText(/Recall proxy 82%/i)).toBeInTheDocument();
    expect(await screen.findByText(/Task failure-rate proxy 11%/i)).toBeInTheDocument();
    expect(await screen.findByText(/Avg event latency proxy 245 ms/i)).toBeInTheDocument();
  });

  it("loads run detail and trace timeline for a run id", async () => {
    render(<App />);
    const user = userEvent.setup();

    await user.clear(screen.getByLabelText("Run ID"));
    await user.type(screen.getByLabelText("Run ID"), "run_001");
    await user.click(screen.getByRole("button", { name: "Load run" }));

    await waitFor(() => {
      expect(screen.getByText("retrieve_candidates")).toBeInTheDocument();
    });
    expect(screen.getByText("AI Agent funding")).toBeInTheDocument();
    expect(screen.getByText("Retrieved candidate items.")).toBeInTheDocument();
    expect(
      screen.getByText(/Candidate task orchestration: 3 tasks/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/Structured stage read surface/i)).toBeInTheDocument();
    expect(screen.getByText(/Planner output/i)).toBeInTheDocument();
    expect(screen.getByText(/Retrieval output/i)).toBeInTheDocument();
    expect(screen.getByText(/Extraction output/i)).toBeInTheDocument();
    expect(screen.getByText(/Evaluation output/i)).toBeInTheDocument();
    expect(screen.getByText(/Run context and business memory/i)).toBeInTheDocument();
    expect(screen.getByText(/Run context keys 2/i)).toBeInTheDocument();
    expect(screen.getByText(/Push history 1 \| documents 1/i)).toBeInTheDocument();
    expect(screen.getByText(/RAG grounding runtime/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Retrieval mode hybrid \| retrievers keyword, bm25, embedding/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Semantic keywords 2 \| trusted sources 2 \| push rules 1/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/RAG guidance applied 1 \| trusted matches 1 \| rule hits 2/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/MCP runtime/i)).toBeInTheDocument();
    expect(screen.getByText(/Browser fallback runtime/i)).toBeInTheDocument();
    expect(screen.getByText(/Notification runtime/i)).toBeInTheDocument();
    expect(screen.getByText(/Configured provider webhook/i)).toBeInTheDocument();
    expect(screen.getByText(/Enabled yes \| used in run yes \| delivery succeeded yes/i)).toBeInTheDocument();
    expect(screen.getByText(/Tool access contract/i)).toBeInTheDocument();
    expect(screen.getByText(/History index runtime/i)).toBeInTheDocument();
    expect(screen.getByText(/Provider opensearch/i)).toBeInTheDocument();
    expect(screen.getByText(/Indexed 2 \| search results 1/i)).toBeInTheDocument();
    expect(screen.getByText(/Contract unified_tool_gateway/i)).toBeInTheDocument();
    expect(screen.getByText(/Search path mcp_gateway \| tool search_news/i)).toBeInTheDocument();
    expect(
      screen.getAllByText(/Trusted-source guidance favored feed-first planning./i)
        .length,
    ).toBeGreaterThan(0);
    expect(screen.getByText(/Configured provider onesearch/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Configured provider playwright_mcp/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/Candidate task ledger/i)).toBeInTheDocument();
    expect(
      screen.getByText(/fetch \| completed \| candidate cand_001/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/evaluate \| completed \| candidate cand_001/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/depends on task_fetch_001/i)).toBeInTheDocument();
    expect(screen.getByText(/attempt 2\/2/i)).toBeInTheDocument();
  });
});
