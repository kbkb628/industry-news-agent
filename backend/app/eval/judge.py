from __future__ import annotations

import json
from typing import Any, Protocol

from app.core.config import Settings


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


class OpenAICompatibleEvalJudge:
    mode = "openai_compatible_judge"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 10.0,
        http_client: Any | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.http_client = http_client

    def _get_http_client(self) -> Any:
        if self.http_client is not None:
            return self.http_client
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("httpx is unavailable for judge requests.") from exc
        return httpx.Client()

    @staticmethod
    def _parse_content(content: str) -> dict[str, Any]:
        payload = json.loads(content)
        return {
            "judge_mode": OpenAICompatibleEvalJudge.mode,
            "judge_score": round(float(payload["judge_score"]), 2),
            "judge_reason": str(payload["judge_reason"]),
            "judge_issues": [str(issue) for issue in payload.get("judge_issues", [])],
        }

    def judge(self, metrics: dict[str, Any]) -> dict[str, Any]:
        client = self._get_http_client()
        response = client.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Return strict JSON with judge_score, judge_reason, "
                            "and judge_issues for the monitor run quality metrics."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(metrics, sort_keys=True),
                    },
                ],
                "temperature": 0,
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        content = payload["choices"][0]["message"]["content"]
        return self._parse_content(str(content))


class FallbackEvalJudge:
    def __init__(self, primary: EvalJudgeProtocol, fallback: EvalJudgeProtocol) -> None:
        self.primary = primary
        self.fallback = fallback

    def judge(self, metrics: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.primary.judge(metrics)
        except Exception as exc:
            result = self.fallback.judge(metrics)
            issues = list(result.get("judge_issues", []))
            if "judge_provider_fallback" not in issues:
                issues.append("judge_provider_fallback")
            result["judge_issues"] = issues
            result["judge_reason"] = f"{result['judge_reason']} Judge provider fallback: {exc}"
            return result


def build_eval_judge(
    *,
    settings: Settings | None = None,
    http_client: Any | None = None,
) -> EvalJudgeProtocol:
    if (
        settings is None
        or settings.judge_provider != "openai_compatible"
        or not settings.judge_base_url
        or not settings.judge_api_key
    ):
        return MockEvalJudge()

    return FallbackEvalJudge(
        primary=OpenAICompatibleEvalJudge(
            base_url=settings.judge_base_url,
            api_key=settings.judge_api_key,
            model=settings.judge_model,
            timeout_seconds=settings.judge_timeout_seconds,
            http_client=http_client,
        ),
        fallback=MockEvalJudge(),
    )
