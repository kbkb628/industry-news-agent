from __future__ import annotations

from typing import Any, Protocol


class EvalJudgeProtocol(Protocol):
    def judge(self, metrics: dict[str, Any]) -> dict[str, Any]: ...


class MockEvalJudge:
    mode = "mock_rule_judge"

    def judge(self, metrics: dict[str, Any]) -> dict[str, Any]:
        issues: list[str] = []
        score = 1.0

        if int(metrics.get("duplicate_push_count", 0)) > 0:
            score -= 0.1
            issues.append("duplicate_push_detected")
        if float(metrics.get("fetch_success_rate", 1.0)) < 1.0:
            score -= 0.15
            issues.append("fetch_degraded")
        if float(metrics.get("trace_completeness", 1.0)) < 1.0:
            score -= 0.15
            issues.append("trace_incomplete")

        judge_score = round(max(0.0, min(1.0, score)), 2)
        if issues:
            reason = "Mock judge detected " + ", ".join(
                issue.replace("_", " ") for issue in issues
            ) + "."
        else:
            reason = "Mock judge found no rule-based quality issues."

        return {
            "judge_mode": self.mode,
            "judge_score": judge_score,
            "judge_reason": reason,
            "judge_issues": issues,
        }
