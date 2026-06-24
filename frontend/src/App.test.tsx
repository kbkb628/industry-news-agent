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
          avg_tool_success_rate: 1,
          avg_fetch_success_rate: 0.75,
          avg_trace_completeness: 0.9,
          latest_eval: {
            eval_id: "eval_001",
            run_id: "run_001",
            topic_id: "topic_001",
            retrieved_count: 4,
            deduped_count: 3,
            push_count: 1,
            tool_success_rate: 1,
          },
        });
      }
      if (path === "/api/monitor/runs/run_001") {
        return respond({
          run_id: "run_001",
          topic_id: "topic_001",
          trigger: "manual",
          status: "completed",
          expanded_queries: ["AI Agent funding"],
          candidate_items: [{ title: "Agent launch" }],
          final_decisions: [{ title: "Agent launch", should_push: true }],
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
        /Supervisor -> Planner -> Retrieval -> Extraction -> Evaluation/i,
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
  });
});
