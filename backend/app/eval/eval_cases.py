from __future__ import annotations


def build_eval_suggestions(
    *,
    push_count: int,
    fetch_success_rate: float,
    trace_completeness: float,
) -> list[str]:
    suggestions: list[str] = []

    if fetch_success_rate < 1.0:
        suggestions.append(
            "Some candidates degraded from fetched content to raw_summary fallback."
        )
    if trace_completeness < 1.0:
        suggestions.append("The monitor trace is missing one or more required node events.")
    if push_count == 0:
        suggestions.append("No candidates met the push threshold for this run.")

    return suggestions
