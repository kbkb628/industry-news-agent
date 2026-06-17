from __future__ import annotations

from typing import Any

import httpx

from app.tools.base import FixtureTool


class NotificationSendTool(FixtureTool):
    def __init__(
        self,
        *,
        provider: str = "none",
        webhook_url: str | None = None,
        http_client: Any | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        super().__init__("notification_send")
        self.provider = provider
        self.webhook_url = webhook_url
        self.http_client = http_client
        self.timeout_seconds = timeout_seconds

    def __call__(
        self,
        *,
        run_id: str,
        topic_id: str,
        push_records: list[dict[str, Any]],
    ) -> object:
        if self.provider == "none":
            return self.success(
                summary="Notification delivery skipped because provider is disabled.",
                data={
                    "status": "skipped",
                    "sent_count": 0,
                    "push_count": len(push_records),
                },
                metadata={"notification_provider": "none"},
            )

        if self.provider == "webhook":
            if not self.webhook_url:
                return self.failure(
                    code="notification_webhook_not_configured",
                    message="Webhook notification provider requires a webhook URL.",
                    summary="Notification delivery failed.",
                    metadata={"notification_provider": "webhook"},
                )

            payload = {
                "run_id": run_id,
                "topic_id": topic_id,
                "push_count": len(push_records),
                "push_records": [
                    _build_push_payload(record) for record in push_records
                ],
            }
            try:
                if self.http_client is None:
                    with httpx.Client() as client:
                        response = client.post(
                            self.webhook_url,
                            json=payload,
                            timeout=self.timeout_seconds,
                        )
                        response.raise_for_status()
                else:
                    response = self.http_client.post(
                        self.webhook_url,
                        json=payload,
                        timeout=self.timeout_seconds,
                    )
                    response.raise_for_status()
            except Exception as exc:
                return self.failure(
                    code="notification_webhook_failed",
                    message=str(exc),
                    summary="Notification delivery failed.",
                    metadata={"notification_provider": "webhook"},
                )

            return self.success(
                summary=f"Sent {len(push_records)} push notification(s).",
                data={
                    "status": "sent",
                    "sent_count": len(push_records),
                    "push_count": len(push_records),
                },
                metadata={"notification_provider": "webhook"},
            )

        return self.failure(
            code="notification_provider_unsupported",
            message=f"Unsupported notification provider: {self.provider}",
            summary="Notification delivery failed.",
            metadata={"notification_provider": self.provider},
        )


def _build_push_payload(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "push_id": record.get("push_id"),
        "title": record.get("title"),
        "url": record.get("url"),
        "summary": record.get("summary"),
        "score": record.get("score"),
        "decision_reason": record.get("decision_reason"),
    }
