import type {
  EvalSummary,
  EventListResponse,
  MonitorRun,
  PushListResponse,
  Topic,
} from "./types";

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`GET ${path} failed with ${response.status}`);
  }
  return (await response.json()) as T;
}

export function fetchTopics(): Promise<Topic[]> {
  return getJson<Topic[]>("/api/topics");
}

export function fetchPushes(): Promise<PushListResponse> {
  return getJson<PushListResponse>("/api/pushes");
}

export function fetchMonitorRun(runId: string): Promise<MonitorRun> {
  return getJson<MonitorRun>(`/api/monitor/runs/${encodeURIComponent(runId)}`);
}

export function fetchEvents(runId: string): Promise<EventListResponse> {
  return getJson<EventListResponse>(
    `/api/monitor/runs/${encodeURIComponent(runId)}/events`,
  );
}

export function fetchEvalSummary(): Promise<EvalSummary> {
  return getJson<EvalSummary>("/api/eval/summary");
}
