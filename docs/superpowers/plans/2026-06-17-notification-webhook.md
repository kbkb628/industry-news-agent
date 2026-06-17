# Webhook Notification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional generic webhook notification channel after push records are persisted, without claiming Slack, email, or enterprise WeChat integrations.

**Architecture:** Keep notifications disabled by default. Register a `notification_send` tool that returns an explicit skipped result when disabled and posts pushed records to a configured webhook only when `NOTIFICATION_PROVIDER=webhook` and `NOTIFICATION_WEBHOOK_URL` are configured. The monitor graph records notification success/failure as events and errors, but notification failures do not roll back persisted push records.

**Tech Stack:** Python stdlib typing, Pydantic settings, existing `ToolResponse`/`LocalToolGateway`, pytest fake HTTP clients.

---

## Guidance Boundaries

- Do not claim Slack, email, or enterprise WeChat delivery.
- Do not make notification delivery required for local tests or the MVP closed loop.
- Do not roll back persisted push records when notification delivery fails.
- Keep the notification payload focused on pushed records, run/topic ids, title, url, summary, score, and decision reason.
- Keep all notification outcomes visible through events, tool results, and errors.

## File Structure

- Modify `backend/app/core/config.py`: add notification provider settings.
- Create `backend/app/tools/notification_tool.py`: no-op and webhook notification sender.
- Modify `backend/app/tools/registry.py`: register `notification_send`.
- Modify `backend/app/agent/nodes.py`: call notification tool after push records are persisted.
- Modify `backend/app/agent/graph.py`: pass notification HTTP client into registry/graph construction if needed.
- Modify `backend/tests/test_tools_and_eval.py`: add settings and tool tests.
- Modify `backend/tests/test_monitor_run_flow.py`: add graph integration tests for success and failure events.
- Modify `backend/README.md`: truthfully document optional generic webhook notification and non-claims.

## Task 1: Settings And Tool Contract

**Files:**
- Modify: `backend/app/core/config.py`
- Create: `backend/app/tools/notification_tool.py`
- Modify: `backend/tests/test_tools_and_eval.py`

- [x] **Step 1: Write failing settings and disabled-tool tests**

```python
def test_settings_accept_notification_webhook_values() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
        notification_provider="webhook",
        notification_webhook_url="https://hooks.example.com/news",
        notification_timeout_seconds=3.5,
    )

    assert settings.notification_provider == "webhook"
    assert settings.notification_webhook_url == "https://hooks.example.com/news"
    assert settings.notification_timeout_seconds == 3.5
```

```python
def test_notification_tool_skips_when_provider_disabled() -> None:
    from app.tools.notification_tool import NotificationSendTool

    response = NotificationSendTool(provider="none")(
        run_id="run_001",
        topic_id="topic_001",
        push_records=[{"push_id": "push_001"}],
    )

    assert response.success is True
    assert response.data["status"] == "skipped"
    assert response.metadata["notification_provider"] == "none"
```

- [x] **Step 2: Run tests to verify they fail**

Run:

```powershell
py -3.12 -m pytest tests/test_tools_and_eval.py::test_settings_accept_notification_webhook_values tests/test_tools_and_eval.py::test_notification_tool_skips_when_provider_disabled -q
```

Expected: FAIL because the settings and tool do not exist.

- [x] **Step 3: Implement minimal settings and disabled tool**

Add:

```python
notification_provider: str = Field(default="none")
notification_webhook_url: str | None = Field(default=None)
notification_timeout_seconds: float = Field(default=10.0, gt=0.0)
```

Implement `NotificationSendTool` with provider `"none"` returning a successful skipped response.

- [x] **Step 4: Run tests to verify they pass**

Run the same focused tests.

Expected: PASS.

## Task 2: Webhook Sender

**Files:**
- Modify: `backend/app/tools/notification_tool.py`
- Modify: `backend/tests/test_tools_and_eval.py`

- [x] **Step 1: Write failing webhook tests**

```python
def test_notification_tool_posts_push_records_to_webhook() -> None:
    from app.tools.notification_tool import NotificationSendTool

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

    class FakeHttpClient:
        def __init__(self) -> None:
            self.requests = []

        def post(self, url: str, json: dict[str, object], timeout: float) -> FakeResponse:
            self.requests.append({"url": url, "json": json, "timeout": timeout})
            return FakeResponse()

    http_client = FakeHttpClient()
    response = NotificationSendTool(
        provider="webhook",
        webhook_url="https://hooks.example.com/news",
        http_client=http_client,
        timeout_seconds=4.0,
    )(
        run_id="run_001",
        topic_id="topic_001",
        push_records=[
            {
                "push_id": "push_001",
                "title": "OpenAI ships agent workflow",
                "url": "https://example.com/agent",
                "summary": "Enterprise agent workflow.",
                "score": 0.91,
                "decision_reason": "score meets threshold",
            }
        ],
    )

    assert response.success is True
    assert response.data["status"] == "sent"
    assert response.data["sent_count"] == 1
    assert http_client.requests[0]["url"] == "https://hooks.example.com/news"
    assert http_client.requests[0]["json"]["run_id"] == "run_001"
    assert http_client.requests[0]["json"]["push_records"][0]["push_id"] == "push_001"
```

```python
def test_notification_tool_fails_when_webhook_url_missing() -> None:
    from app.tools.notification_tool import NotificationSendTool

    response = NotificationSendTool(provider="webhook")(
        run_id="run_001",
        topic_id="topic_001",
        push_records=[{"push_id": "push_001"}],
    )

    assert response.success is False
    assert response.error.code == "notification_webhook_not_configured"
```

- [x] **Step 2: Run tests to verify they fail**

Run focused notification tests.

Expected: FAIL because webhook behavior is not implemented.

- [x] **Step 3: Implement webhook sender**

Implement a `post` call with payload:

```python
{
    "run_id": run_id,
    "topic_id": topic_id,
    "push_count": len(push_records),
    "push_records": [...focused fields...],
}
```

Use `httpx.Client()` only when no fake client is injected.

- [x] **Step 4: Run tests to verify they pass**

Run focused notification tests.

Expected: PASS.

## Task 3: Registry And Monitor Graph Integration

**Files:**
- Modify: `backend/app/tools/registry.py`
- Modify: `backend/app/agent/nodes.py`
- Modify: `backend/app/agent/graph.py`
- Modify: `backend/tests/test_monitor_run_flow.py`

- [x] **Step 1: Write failing graph integration tests**

Add tests that prove:

- when push records exist and webhook provider is enabled, the monitor graph calls `notification_send` after push persistence and records `notification_sent`
- when notification fails, push records remain persisted, state gets an error, and a `node_failed` notification event is recorded

- [x] **Step 2: Run tests to verify they fail**

Run focused monitor tests.

Expected: FAIL because graph integration does not call notification yet.

- [x] **Step 3: Implement graph integration**

Update `persist_push_records_node` to accept an optional gateway and call:

```python
gateway.call(
    "notification_send",
    run_id=str(state["run_id"]),
    topic_id=str(state["topic_id"]),
    push_records=state["push_records"],
)
```

Rules:

- record successful `sent` as `notification_sent`
- record disabled/skipped as `notification_skipped`
- on failure, append to `errors` and add `node_failed`; do not raise
- do nothing when no gateway is supplied, preserving direct node tests

- [x] **Step 4: Run tests to verify they pass**

Run focused monitor tests.

Expected: PASS.

## Task 4: Documentation, Review, Verification, Commit

**Files:**
- Modify: `backend/README.md`
- Modify: this plan document

- [x] **Step 1: Update README**

Add included capability:

- optional generic webhook notification channel after persisted push records

Keep not claimed:

- Slack-specific delivery
- email delivery
- enterprise WeChat delivery
- production notification retry/queue hardening

- [x] **Step 2: Run subagent reviews**

Use two read-only subagents:

- spec compliance against `DEVELOPMENT_GUIDE.md` and this plan
- code quality and regression risk

Status: code quality review completed and findings were addressed. Spec
compliance review completed with no blocking findings.

- [x] **Step 2a: Address code-review hardening**

Add tests and implementation for:

- default tool registry includes `notification_send`
- webhook HTTP/client exceptions are normalized to
  `notification_webhook_failed` with webhook provider metadata

- [x] **Step 3: Run verification**

From `backend`:

```powershell
py -3.12 -m pytest -q
py -3.12 -m compileall app
```

From repo root:

```powershell
docker compose config --quiet
git diff --check
git status --short --branch
```

- [ ] **Step 4: Commit and push**

```powershell
git add docs/superpowers/plans/2026-06-17-notification-webhook.md backend/app/core/config.py backend/app/tools/notification_tool.py backend/app/tools/registry.py backend/app/agent/nodes.py backend/app/agent/graph.py backend/tests/test_tools_and_eval.py backend/tests/test_monitor_run_flow.py backend/README.md
git commit -m "feat: add webhook notification channel"
git push
```
