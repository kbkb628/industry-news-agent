export type Topic = {
  topic_id: string;
  name: string;
  description: string;
  seed_keywords: string[];
  trusted_sources: string[];
  exclude_keywords: string[];
  push_threshold: number;
  cooldown_hours: number;
  enabled: boolean;
  schedule_cron?: string | null;
  created_at?: string;
  updated_at?: string;
};

export type PushRecord = {
  push_id: string;
  run_id: string;
  topic_id: string;
  candidate_id: string;
  extracted_id?: string | null;
  should_push: boolean;
  score: number;
  decision_reason?: string | null;
  pushed_at?: string | null;
};

export type PushListResponse = {
  topic_id?: string | null;
  pushes: PushRecord[];
};

export type MonitorRun = {
  run_id: string;
  topic_id: string;
  trigger: string;
  status: "pending" | "running" | "completed" | "failed";
  run_context?: Record<string, unknown>;
  business_memory?: {
    push_history?: Record<string, unknown>[];
    documents?: Record<string, unknown>[];
    [key: string]: unknown;
  };
  expanded_queries?: string[];
  candidate_items?: Record<string, unknown>[];
  final_decisions?: Record<string, unknown>[];
  planner_output?: {
    expanded_queries?: string[];
    source_plan?: Record<string, unknown>[];
    planning_reasons?: string[];
  };
  retrieval_output?: {
    candidate_pool?: Record<string, unknown>[];
    provider_fallbacks?: Record<string, unknown>[];
  };
  extraction_output?: {
    fetched_contents?: Record<string, unknown>[];
    evidence_items?: Record<string, unknown>[];
  };
  evaluation_output?: {
    final_decisions?: Record<string, unknown>[];
    push_records?: Record<string, unknown>[];
  };
  history_index_result?: {
    provider?: string;
    indexed_count?: number;
    search?: {
      query?: string;
      returned_count?: number;
      items?: Record<string, unknown>[];
    };
  };
  integration_runtime?: {
    mcp?: {
      configured_provider?: string;
      enabled?: boolean;
      used_in_run?: boolean;
      fallback_used?: boolean;
    };
    browser?: {
      configured_provider?: string;
      enabled?: boolean;
      used_in_run?: boolean;
      fallback_used?: boolean;
      allowed_domains?: string[];
    };
    tool_access?: {
      contract?: string;
      search?: {
        provider_path?: string;
        tool_name?: string;
      };
      browser?: {
        provider_path?: string;
        tool_name?: string;
      };
      notification?: {
        provider_path?: string;
        tool_name?: string;
      };
    };
  };
  candidate_task_summary?: {
    task_count?: number;
    completed_count?: number;
    failed_count?: number;
    skipped_count?: number;
    fetch_completed_count?: number;
    extract_completed_count?: number;
    evaluate_completed_count?: number;
  };
  errors?: Record<string, unknown>[];
  started_at?: string | null;
  finished_at?: string | null;
};

export type RunEvent = {
  event_id: string;
  run_id: string;
  topic_id: string;
  event_type: string;
  node: string;
  message: string;
  payload?: Record<string, unknown>;
  elapsed_ms?: number | null;
  created_at?: string | null;
};

export type EventListResponse = {
  run_id: string;
  events: RunEvent[];
};

export type CandidateTaskRecord = {
  task_id: string;
  run_id: string;
  candidate_id: string;
  stage: string;
  status: string;
  attempt?: number;
  max_attempts?: number;
  depends_on_task_ids?: string[];
  input_ref?: Record<string, unknown>;
  output_ref?: Record<string, unknown>;
  error_code?: string | null;
  error_message?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  created_at?: string | null;
};

export type CandidateTaskListResponse = {
  items: CandidateTaskRecord[];
};

export type EvalResult = {
  eval_id: string;
  run_id: string;
  topic_id: string;
  retrieved_count: number;
  deduped_count: number;
  dedup_rate?: number;
  push_count: number;
  duplicate_push_count?: number;
  tool_success_rate: number;
  fetch_success_rate?: number;
  trace_completeness?: number;
  raw_summary_count?: number;
  browser_fallback_count?: number;
  provider_fallback_count?: number;
  candidate_recall_proxy?: number;
  false_positive_proxy_count?: number;
  candidate_task_failure_rate?: number;
  avg_event_latency_ms?: number;
  runtime_cost_proxy?: {
    tool_calls?: number;
    browser_fallbacks?: number;
    model_decisions?: number;
  };
  judge_mode?: string;
  judge_score?: number;
  judge_reason?: string;
  judge_issues?: string[];
  suggestions?: string[];
  created_at?: string | null;
};

export type EvalSummary = {
  run_count: number;
  total_push_count: number;
  total_duplicate_push_count: number;
  total_raw_summary_count: number;
  total_browser_fallback_count: number;
  total_provider_fallback_count: number;
  total_false_positive_proxy_count: number;
  avg_tool_success_rate: number;
  avg_fetch_success_rate: number;
  avg_trace_completeness: number;
  avg_candidate_recall_proxy: number;
  avg_candidate_task_failure_rate: number;
  avg_event_latency_ms: number;
  latest_eval: EvalResult;
};
