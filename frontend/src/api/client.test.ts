import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  fetchEvalSummary,
  fetchCandidateTasks,
  fetchEvents,
  fetchMonitorRun,
  fetchPushes,
  fetchTopics,
} from "./client";

const jsonResponse = (body: unknown, ok = true) =>
  Promise.resolve({
    ok,
    status: ok ? 200 : 500,
    json: () => Promise.resolve(body),
  } as Response);

describe("api client", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    fetchMock.mockReset();
  });

  it("requests the existing backend endpoint paths", async () => {
    fetchMock.mockImplementation((path: string) => {
      if (path === "/api/topics") return jsonResponse([]);
      if (path === "/api/pushes") return jsonResponse({ pushes: [] });
      if (path === "/api/monitor/runs/run_001") {
        return jsonResponse({
          run_id: "run_001",
          topic_id: "topic_001",
          trigger: "manual",
          status: "completed",
        });
      }
      if (path === "/api/monitor/runs/run_001/events") {
        return jsonResponse({ run_id: "run_001", events: [] });
      }
      if (path === "/api/monitor/runs/run_001/candidate-tasks") {
        return jsonResponse({ items: [] });
      }
      if (path === "/api/eval/summary") {
        return jsonResponse({
          run_count: 1,
          total_push_count: 0,
          total_duplicate_push_count: 0,
          total_raw_summary_count: 0,
          total_browser_fallback_count: 0,
          total_provider_fallback_count: 0,
          avg_tool_success_rate: 1,
          avg_fetch_success_rate: 1,
          avg_trace_completeness: 1,
          latest_eval: {
            eval_id: "eval_001",
            run_id: "run_001",
            topic_id: "topic_001",
            retrieved_count: 0,
            deduped_count: 0,
            dedup_rate: 0,
            push_count: 0,
            duplicate_push_count: 0,
            tool_success_rate: 1,
            fetch_success_rate: 1,
            trace_completeness: 1,
          },
        });
      }
      throw new Error(`unexpected path ${path}`);
    });

    await fetchTopics();
    await fetchPushes();
    await fetchMonitorRun("run_001");
    await fetchEvents("run_001");
    await fetchCandidateTasks("run_001");
    await fetchEvalSummary();

    expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/topics");
    expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/pushes");
    expect(fetchMock).toHaveBeenNthCalledWith(3, "/api/monitor/runs/run_001");
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      "/api/monitor/runs/run_001/events",
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      5,
      "/api/monitor/runs/run_001/candidate-tasks",
    );
    expect(fetchMock).toHaveBeenNthCalledWith(6, "/api/eval/summary");
  });

  it("throws a readable error when a backend request fails", async () => {
    fetchMock.mockReturnValue(jsonResponse({ detail: "boom" }, false));

    await expect(fetchTopics()).rejects.toThrow(
      "GET /api/topics failed with 500",
    );
  });
});
