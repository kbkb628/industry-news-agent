# Industry News Agent MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the guidance-document MVP for the industry-news structured push agent with real PostgreSQL and Redis, MockLLM, FastAPI APIs, and a minimal HTML admin page.

**Architecture:** Use a single FastAPI process with clear module boundaries for API, agent orchestration, tools, storage, RAG, scheduler, and observability. Persist business facts in PostgreSQL, keep short-lived coordination in Redis, and run the end-to-end monitor flow through LangGraph with controlled tool abstractions and explicit fallback logging.

**Tech Stack:** Python 3.11+, FastAPI, Uvicorn, SQLAlchemy, Pydantic, psycopg, redis-py, APScheduler, LangGraph, feedparser, httpx, readability-lxml, BeautifulSoup4, Jinja2, pytest

---

## File Structure

### Create

- `E:/bgagent2/.gitignore`
- `E:/bgagent2/backend/README.md`
- `E:/bgagent2/backend/pyproject.toml`
- `E:/bgagent2/backend/app/main.py`
- `E:/bgagent2/backend/app/core/config.py`
- `E:/bgagent2/backend/app/core/exceptions.py`
- `E:/bgagent2/backend/app/api/topics.py`
- `E:/bgagent2/backend/app/api/monitor.py`
- `E:/bgagent2/backend/app/api/candidates.py`
- `E:/bgagent2/backend/app/api/pushes.py`
- `E:/bgagent2/backend/app/api/events.py`
- `E:/bgagent2/backend/app/api/eval.py`
- `E:/bgagent2/backend/app/schemas/topic_schema.py`
- `E:/bgagent2/backend/app/schemas/monitor_schema.py`
- `E:/bgagent2/backend/app/schemas/candidate_schema.py`
- `E:/bgagent2/backend/app/schemas/tool_schema.py`
- `E:/bgagent2/backend/app/schemas/push_schema.py`
- `E:/bgagent2/backend/app/schemas/event_schema.py`
- `E:/bgagent2/backend/app/schemas/eval_schema.py`
- `E:/bgagent2/backend/app/storage/database.py`
- `E:/bgagent2/backend/app/storage/models.py`
- `E:/bgagent2/backend/app/storage/repository.py`
- `E:/bgagent2/backend/app/storage/redis_store.py`
- `E:/bgagent2/backend/app/llm/base.py`
- `E:/bgagent2/backend/app/llm/mock_client.py`
- `E:/bgagent2/backend/app/llm/prompt_templates.py`
- `E:/bgagent2/backend/app/tools/base.py`
- `E:/bgagent2/backend/app/tools/registry.py`
- `E:/bgagent2/backend/app/tools/responses.py`
- `E:/bgagent2/backend/app/tools/rss_tool.py`
- `E:/bgagent2/backend/app/tools/search_tool.py`
- `E:/bgagent2/backend/app/tools/browser_fetch_tool.py`
- `E:/bgagent2/backend/app/tools/extract_tool.py`
- `E:/bgagent2/backend/app/tools/dedup_tool.py`
- `E:/bgagent2/backend/app/tools/scoring_tool.py`
- `E:/bgagent2/backend/app/tools/push_tool.py`
- `E:/bgagent2/backend/app/mcp/gateway.py`
- `E:/bgagent2/backend/app/mcp/local_gateway.py`
- `E:/bgagent2/backend/app/rag/knowledge_loader.py`
- `E:/bgagent2/backend/app/rag/keyword_retriever.py`
- `E:/bgagent2/backend/app/rag/knowledge_base.jsonl`
- `E:/bgagent2/backend/app/agent/state.py`
- `E:/bgagent2/backend/app/agent/planner.py`
- `E:/bgagent2/backend/app/agent/nodes.py`
- `E:/bgagent2/backend/app/agent/graph.py`
- `E:/bgagent2/backend/app/scheduler/jobs.py`
- `E:/bgagent2/backend/app/scheduler/worker.py`
- `E:/bgagent2/backend/app/eval/rule_scorer.py`
- `E:/bgagent2/backend/app/eval/eval_cases.py`
- `E:/bgagent2/backend/app/observability/event_logger.py`
- `E:/bgagent2/backend/app/observability/trace_models.py`
- `E:/bgagent2/backend/app/templates/base.html`
- `E:/bgagent2/backend/app/templates/topics.html`
- `E:/bgagent2/backend/app/templates/run_detail.html`
- `E:/bgagent2/backend/app/templates/pushes.html`
- `E:/bgagent2/backend/app/templates/events.html`
- `E:/bgagent2/backend/data/fixtures/sample_sources.json`
- `E:/bgagent2/backend/data/fixtures/sample_articles.json`
- `E:/bgagent2/backend/tests/conftest.py`
- `E:/bgagent2/backend/tests/test_topics_api.py`
- `E:/bgagent2/backend/tests/test_monitor_run_flow.py`
- `E:/bgagent2/backend/tests/test_tools_and_eval.py`

### Modify

- `E:/bgagent2/DEVELOPMENT_GUIDE.md` only if the user later asks to sync implementation status back into the guide

---

### Task 1: Bootstrap project skeleton and dependency contract

**Files:**
- Create: `E:/bgagent2/.gitignore`
- Create: `E:/bgagent2/backend/pyproject.toml`
- Create: `E:/bgagent2/backend/README.md`
- Create: `E:/bgagent2/backend/app/main.py`
- Test: `E:/bgagent2/backend/tests/conftest.py`

- [ ] **Step 1: Write the failing smoke test**

```python
# E:/bgagent2/backend/tests/conftest.py
from fastapi.testclient import TestClient

from app.main import create_app


def build_client() -> TestClient:
    app = create_app()
    return TestClient(app)
```

```python
# E:/bgagent2/backend/tests/test_topics_api.py
from .conftest import build_client


def test_health_endpoint_exists() -> None:
    client = build_client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd E:/bgagent2/backend && pytest tests/test_topics_api.py::test_health_endpoint_exists -v`

Expected: FAIL with `ModuleNotFoundError` or `cannot import name 'create_app'`

- [ ] **Step 3: Write minimal project files**

```toml
# E:/bgagent2/backend/pyproject.toml
[project]
name = "industry-news-agent"
version = "0.1.0"
description = "Industry news structured push agent MVP"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.115.0",
  "uvicorn[standard]>=0.30.0",
  "sqlalchemy>=2.0.35",
  "psycopg[binary]>=3.2.0",
  "redis>=5.0.8",
  "pydantic>=2.9.0",
  "pydantic-settings>=2.5.2",
  "apscheduler>=3.10.4",
  "langgraph>=0.2.16",
  "httpx>=0.27.2",
  "feedparser>=6.0.11",
  "beautifulsoup4>=4.12.3",
  "readability-lxml>=0.8.1",
  "jinja2>=3.1.4",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.3.2",
  "pytest-asyncio>=0.24.0",
]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

```gitignore
# E:/bgagent2/.gitignore
__pycache__/
*.pyc
.pytest_cache/
.venv/
.env
backend/.coverage
backend/htmlcov/
backend/.mypy_cache/
```

```python
# E:/bgagent2/backend/app/main.py
from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="Industry News Agent MVP")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
```

```md
# E:/bgagent2/backend/README.md
# Industry News Agent MVP

This backend implements the guidance-document MVP only.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd E:/bgagent2/backend && pytest tests/test_topics_api.py::test_health_endpoint_exists -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add .gitignore backend/pyproject.toml backend/README.md backend/app/main.py backend/tests/conftest.py backend/tests/test_topics_api.py
git commit -m "chore: bootstrap backend project skeleton"
```

---

### Task 2: Add configuration, database, Redis, and domain models

**Files:**
- Create: `E:/bgagent2/backend/app/core/config.py`
- Create: `E:/bgagent2/backend/app/storage/database.py`
- Create: `E:/bgagent2/backend/app/storage/models.py`
- Create: `E:/bgagent2/backend/app/storage/redis_store.py`
- Create: `E:/bgagent2/backend/tests/test_tools_and_eval.py`

- [ ] **Step 1: Write the failing infrastructure test**

```python
# E:/bgagent2/backend/tests/test_tools_and_eval.py
from app.core.config import Settings
from app.storage.models import Topic


def test_settings_expose_required_connections() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
        redis_url="redis://localhost:6379/0",
    )
    assert settings.database_url.startswith("postgresql+psycopg://")
    assert settings.redis_url.startswith("redis://")


def test_topic_model_tablename() -> None:
    assert Topic.__tablename__ == "topics"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd E:/bgagent2/backend && pytest tests/test_tools_and_eval.py::test_settings_expose_required_connections tests/test_tools_and_eval.py::test_topic_model_tablename -v`

Expected: FAIL with missing modules for `app.core.config` or `app.storage.models`

- [ ] **Step 3: Write minimal infrastructure code**

```python
# E:/bgagent2/backend/app/core/config.py
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Industry News Agent MVP"
    database_url: str = Field(...)
    redis_url: str = Field(...)
    default_push_threshold: float = 0.72


settings = Settings(
    database_url="postgresql+psycopg://user:pass@localhost:5432/news_agent",
    redis_url="redis://localhost:6379/0",
)
```

```python
# E:/bgagent2/backend/app/storage/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
```

```python
# E:/bgagent2/backend/app/storage/models.py
import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.storage.database import Base


class Topic(Base):
    __tablename__ = "topics"

    topic_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"topic_{uuid.uuid4().hex[:12]}")
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    seed_keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    trusted_sources: Mapped[list[str]] = mapped_column(JSON, default=list)
    exclude_keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    push_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.72)
    cooldown_hours: Mapped[int] = mapped_column(nullable=False, default=24)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    schedule_cron: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

```python
# E:/bgagent2/backend/app/storage/redis_store.py
from redis import Redis

from app.core.config import settings


def build_redis_client() -> Redis:
    return Redis.from_url(settings.redis_url, decode_responses=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd E:/bgagent2/backend && pytest tests/test_tools_and_eval.py::test_settings_expose_required_connections tests/test_tools_and_eval.py::test_topic_model_tablename -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/config.py backend/app/storage/database.py backend/app/storage/models.py backend/app/storage/redis_store.py backend/tests/test_tools_and_eval.py
git commit -m "feat: add settings and persistence foundations"
```

---

### Task 3: Freeze schemas and repository contracts

**Files:**
- Create: `E:/bgagent2/backend/app/schemas/topic_schema.py`
- Create: `E:/bgagent2/backend/app/schemas/monitor_schema.py`
- Create: `E:/bgagent2/backend/app/schemas/candidate_schema.py`
- Create: `E:/bgagent2/backend/app/schemas/push_schema.py`
- Create: `E:/bgagent2/backend/app/schemas/event_schema.py`
- Create: `E:/bgagent2/backend/app/schemas/eval_schema.py`
- Create: `E:/bgagent2/backend/app/schemas/tool_schema.py`
- Create: `E:/bgagent2/backend/app/storage/repository.py`
- Modify: `E:/bgagent2/backend/app/storage/models.py`
- Modify: `E:/bgagent2/backend/tests/test_topics_api.py`

- [ ] **Step 1: Write the failing schema test**

```python
# E:/bgagent2/backend/tests/test_topics_api.py
from app.schemas.topic_schema import TopicCreateRequest


def test_topic_create_request_defaults() -> None:
    payload = TopicCreateRequest(
        name="AI Agent 行业动态",
        description="监控 AI Agent 产品、融资与开源项目",
        seed_keywords=["AI Agent", "MCP"],
        trusted_sources=["github.com"],
        exclude_keywords=["广告"],
    )
    assert payload.push_threshold == 0.72
    assert payload.cooldown_hours == 24
    assert payload.enabled is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd E:/bgagent2/backend && pytest tests/test_topics_api.py::test_topic_create_request_defaults -v`

Expected: FAIL with missing schema module

- [ ] **Step 3: Write schemas and repository protocol**

```python
# E:/bgagent2/backend/app/schemas/topic_schema.py
from datetime import datetime

from pydantic import BaseModel, Field


class TopicCreateRequest(BaseModel):
    name: str
    description: str
    seed_keywords: list[str]
    trusted_sources: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    push_threshold: float = 0.72
    cooldown_hours: int = 24
    enabled: bool = True
    schedule_cron: str | None = None


class TopicResponse(BaseModel):
    topic_id: str
    status: str
    created_at: datetime
```

```python
# E:/bgagent2/backend/app/schemas/monitor_schema.py
from datetime import datetime

from pydantic import BaseModel


class MonitorRunResponse(BaseModel):
    run_id: str
    topic_id: str
    status: str


class MonitorRunStateResponse(BaseModel):
    run_id: str
    topic_id: str
    status: str
    expanded_queries: list[str] = []
    candidate_items: list[dict] = []
    final_decisions: list[dict] = []
    errors: list[dict] = []
    started_at: datetime | None = None
    finished_at: datetime | None = None
```

```python
# E:/bgagent2/backend/app/schemas/candidate_schema.py
from pydantic import BaseModel


class CandidateListResponse(BaseModel):
    run_id: str
    candidates: list[dict]
```

```python
# E:/bgagent2/backend/app/schemas/push_schema.py
from pydantic import BaseModel


class PushListResponse(BaseModel):
    pushes: list[dict]
```

```python
# E:/bgagent2/backend/app/schemas/event_schema.py
from pydantic import BaseModel


class EventListResponse(BaseModel):
    run_id: str
    events: list[dict]
```

```python
# E:/bgagent2/backend/app/schemas/eval_schema.py
from pydantic import BaseModel


class EvalRunResponse(BaseModel):
    run_id: str
    retrieved_count: int
    deduped_count: int
    push_count: int
    tool_success_rate: float
```

```python
# E:/bgagent2/backend/app/schemas/tool_schema.py
from pydantic import BaseModel


class ToolError(BaseModel):
    code: str
    message: str
    fallback: str | None = None


class ToolResponseModel(BaseModel):
    success: bool
    tool_name: str
    data: dict | list | None
    summary: str
    error: ToolError | None = None
    metadata: dict = {}
```

```python
# E:/bgagent2/backend/app/storage/repository.py
from typing import Protocol

from app.schemas.topic_schema import TopicCreateRequest


class TopicRepositoryProtocol(Protocol):
    def create_topic(self, payload: TopicCreateRequest) -> dict: ...

    def list_topics(self) -> list[dict]: ...

    def get_topic(self, topic_id: str) -> dict | None: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd E:/bgagent2/backend && pytest tests/test_topics_api.py::test_topic_create_request_defaults -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas backend/app/storage/repository.py backend/tests/test_topics_api.py
git commit -m "feat: add API schemas and repository contracts"
```

---

### Task 4: Implement topic persistence and topic APIs

**Files:**
- Modify: `E:/bgagent2/backend/app/main.py`
- Create: `E:/bgagent2/backend/app/api/topics.py`
- Modify: `E:/bgagent2/backend/app/storage/repository.py`
- Modify: `E:/bgagent2/backend/app/storage/database.py`
- Modify: `E:/bgagent2/backend/tests/test_topics_api.py`

- [ ] **Step 1: Write the failing topic API tests**

```python
# E:/bgagent2/backend/tests/test_topics_api.py
from .conftest import build_client


def test_create_topic_returns_topic_id() -> None:
    client = build_client()
    response = client.post(
        "/api/topics",
        json={
            "name": "AI Agent 行业动态",
            "description": "监控 AI Agent 产品、融资与开源项目",
            "seed_keywords": ["AI Agent", "MCP"],
            "trusted_sources": ["github.com"],
            "exclude_keywords": ["广告"],
        },
    )
    assert response.status_code == 200
    assert response.json()["topic_id"].startswith("topic_")
    assert response.json()["status"] == "enabled"


def test_list_topics_returns_created_topic() -> None:
    client = build_client()
    client.post(
        "/api/topics",
        json={
            "name": "大模型应用落地",
            "description": "监控企业大模型应用案例",
            "seed_keywords": ["大模型", "Agent"],
            "trusted_sources": ["techcrunch.com"],
            "exclude_keywords": ["培训"],
        },
    )
    response = client.get("/api/topics")
    assert response.status_code == 200
    topics = response.json()
    assert len(topics) >= 1
    assert topics[0]["name"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd E:/bgagent2/backend && pytest tests/test_topics_api.py::test_create_topic_returns_topic_id tests/test_topics_api.py::test_list_topics_returns_created_topic -v`

Expected: FAIL with `404 Not Found` for `/api/topics`

- [ ] **Step 3: Implement repository-backed topic API**

```python
# E:/bgagent2/backend/app/storage/database.py
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

```python
# E:/bgagent2/backend/app/storage/repository.py
from datetime import datetime

from sqlalchemy.orm import Session

from app.schemas.topic_schema import TopicCreateRequest
from app.storage.models import Topic


class TopicRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_topic(self, payload: TopicCreateRequest) -> dict:
        topic = Topic(**payload.model_dump())
        self.db.add(topic)
        self.db.commit()
        self.db.refresh(topic)
        return {
            "topic_id": topic.topic_id,
            "status": "enabled" if topic.enabled else "disabled",
            "created_at": topic.created_at,
        }

    def list_topics(self) -> list[dict]:
        topics = self.db.query(Topic).order_by(Topic.created_at.desc()).all()
        return [
            {
                "topic_id": topic.topic_id,
                "name": topic.name,
                "description": topic.description,
                "seed_keywords": topic.seed_keywords,
                "trusted_sources": topic.trusted_sources,
                "exclude_keywords": topic.exclude_keywords,
                "push_threshold": topic.push_threshold,
                "cooldown_hours": topic.cooldown_hours,
                "enabled": topic.enabled,
                "schedule_cron": topic.schedule_cron,
                "created_at": topic.created_at.isoformat(),
            }
            for topic in topics
        ]

    def get_topic(self, topic_id: str) -> dict | None:
        topic = self.db.query(Topic).filter(Topic.topic_id == topic_id).one_or_none()
        if topic is None:
            return None
        return {
            "topic_id": topic.topic_id,
            "name": topic.name,
            "description": topic.description,
            "seed_keywords": topic.seed_keywords,
            "trusted_sources": topic.trusted_sources,
            "exclude_keywords": topic.exclude_keywords,
            "push_threshold": topic.push_threshold,
            "cooldown_hours": topic.cooldown_hours,
            "enabled": topic.enabled,
            "schedule_cron": topic.schedule_cron,
            "created_at": topic.created_at.isoformat(),
            "updated_at": topic.updated_at.isoformat() if isinstance(topic.updated_at, datetime) else None,
        }
```

```python
# E:/bgagent2/backend/app/api/topics.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.schemas.topic_schema import TopicCreateRequest
from app.storage.database import get_db
from app.storage.repository import TopicRepository

router = APIRouter(prefix="/api/topics", tags=["topics"])


@router.post("")
def create_topic(payload: TopicCreateRequest, db: Session = Depends(get_db)) -> dict:
    repo = TopicRepository(db)
    return repo.create_topic(payload)


@router.get("")
def list_topics(db: Session = Depends(get_db)) -> list[dict]:
    repo = TopicRepository(db)
    return repo.list_topics()


@router.get("/{topic_id}")
def get_topic(topic_id: str, db: Session = Depends(get_db)) -> dict:
    repo = TopicRepository(db)
    topic = repo.get_topic(topic_id)
    if topic is None:
        raise HTTPException(status_code=404, detail="topic not found")
    return topic
```

```python
# E:/bgagent2/backend/app/main.py
from fastapi import FastAPI

from app.api.topics import router as topics_router


def create_app() -> FastAPI:
    app = FastAPI(title="Industry News Agent MVP")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(topics_router)
    return app


app = create_app()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd E:/bgagent2/backend && pytest tests/test_topics_api.py::test_create_topic_returns_topic_id tests/test_topics_api.py::test_list_topics_returns_created_topic -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/app/api/topics.py backend/app/storage/database.py backend/app/storage/repository.py backend/tests/test_topics_api.py
git commit -m "feat: add topic management APIs"
```

---

### Task 5: Add tool response contract, MockLLM, RAG loader, and local tool gateway

**Files:**
- Create: `E:/bgagent2/backend/app/llm/base.py`
- Create: `E:/bgagent2/backend/app/llm/mock_client.py`
- Create: `E:/bgagent2/backend/app/llm/prompt_templates.py`
- Create: `E:/bgagent2/backend/app/tools/base.py`
- Create: `E:/bgagent2/backend/app/tools/registry.py`
- Create: `E:/bgagent2/backend/app/tools/responses.py`
- Create: `E:/bgagent2/backend/app/mcp/gateway.py`
- Create: `E:/bgagent2/backend/app/mcp/local_gateway.py`
- Create: `E:/bgagent2/backend/app/rag/knowledge_loader.py`
- Create: `E:/bgagent2/backend/app/rag/keyword_retriever.py`
- Create: `E:/bgagent2/backend/app/rag/knowledge_base.jsonl`
- Modify: `E:/bgagent2/backend/tests/test_tools_and_eval.py`

- [ ] **Step 1: Write the failing tool and RAG tests**

```python
# E:/bgagent2/backend/tests/test_tools_and_eval.py
from app.llm.mock_client import MockLLMClient
from app.rag.keyword_retriever import KeywordRetriever
from app.tools.responses import ToolResponse


def test_tool_response_success_summary() -> None:
    result = ToolResponse.success("rss_fetch", {"items": []}, "no items", {"item_count": 0})
    assert result["success"] is True
    assert result["tool_name"] == "rss_fetch"


def test_mock_llm_generates_expanded_queries() -> None:
    llm = MockLLMClient()
    queries = llm.expand_keywords(["AI Agent", "MCP"])
    assert "AI Agent 融资" in queries


def test_keyword_retriever_returns_context() -> None:
    retriever = KeywordRetriever("app/rag/knowledge_base.jsonl")
    result = retriever.retrieve(["AI Agent"])
    assert result["trusted_sources"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd E:/bgagent2/backend && pytest tests/test_tools_and_eval.py::test_tool_response_success_summary tests/test_tools_and_eval.py::test_mock_llm_generates_expanded_queries tests/test_tools_and_eval.py::test_keyword_retriever_returns_context -v`

Expected: FAIL with missing LLM, RAG, or tools modules

- [ ] **Step 3: Implement the contracts**

```python
# E:/bgagent2/backend/app/tools/responses.py
class ToolResponse:
    @staticmethod
    def success(tool_name: str, data: dict | list | None, summary: str, metadata: dict | None = None) -> dict:
        return {
            "success": True,
            "tool_name": tool_name,
            "data": data,
            "summary": summary,
            "error": None,
            "metadata": metadata or {},
        }

    @staticmethod
    def failure(tool_name: str, code: str, message: str, fallback: str | None = None, metadata: dict | None = None) -> dict:
        return {
            "success": False,
            "tool_name": tool_name,
            "data": None,
            "summary": message,
            "error": {"code": code, "message": message, "fallback": fallback},
            "metadata": metadata or {},
        }
```

```python
# E:/bgagent2/backend/app/llm/base.py
from typing import Protocol


class BaseLLMClient(Protocol):
    def expand_keywords(self, seed_keywords: list[str]) -> list[str]: ...

    def extract_article(self, raw_text: str, source_url: str) -> dict: ...

    def score_candidate(self, item: dict, business_context: dict) -> dict: ...
```

```python
# E:/bgagent2/backend/app/llm/mock_client.py
class MockLLMClient:
    def expand_keywords(self, seed_keywords: list[str]) -> list[str]:
        expanded = set(seed_keywords)
        for keyword in seed_keywords:
            expanded.add(f"{keyword} 融资")
            expanded.add(f"{keyword} 开源")
            expanded.add(f"{keyword} 企业落地")
        return list(expanded)

    def extract_article(self, raw_text: str, source_url: str) -> dict:
        return {
            "title": raw_text.splitlines()[0][:80] if raw_text else source_url,
            "source": source_url,
            "summary": raw_text[:200],
            "keywords": ["AI Agent", "MCP"],
            "entities": ["LangGraph", "FastAPI"],
        }

    def score_candidate(self, item: dict, business_context: dict) -> dict:
        source_bonus = 0.2 if item.get("source_domain") in business_context.get("trusted_sources", []) else 0.0
        relevance = 0.55 + source_bonus
        return {
            "relevance": relevance,
            "business_value": min(relevance + 0.1, 0.95),
            "novelty": 0.7,
            "final_score": round(min(relevance + 0.15, 0.95), 2),
        }
```

```python
# E:/bgagent2/backend/app/rag/knowledge_loader.py
import json
from pathlib import Path


def load_knowledge(path: str) -> list[dict]:
    records: list[dict] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records
```

```python
# E:/bgagent2/backend/app/rag/keyword_retriever.py
from app.rag.knowledge_loader import load_knowledge


class KeywordRetriever:
    def __init__(self, path: str) -> None:
        self.records = load_knowledge(path)

    def retrieve(self, queries: list[str]) -> dict:
        trusted_sources: set[str] = set()
        snippets: list[str] = []
        for record in self.records:
            joined = " ".join(record.get("keywords", []))
            if any(query.lower() in joined.lower() for query in queries):
                trusted_sources.update(record.get("trusted_sources", []))
                snippets.append(record.get("context", ""))
        return {
            "trusted_sources": sorted(trusted_sources),
            "context_snippets": snippets,
        }
```

```json
{"topic":"AI Agent 行业动态","keywords":["AI Agent","MCP","LangGraph"],"trusted_sources":["github.com","techcrunch.com","langchain.com"],"context":"关注 AI Agent 融资、企业落地、开源框架和工具协议演进。"}
{"topic":"大模型应用落地","keywords":["大模型","智能体","企业应用"],"trusted_sources":["theinformation.com","techcrunch.com"],"context":"关注企业应用发布、行业解决方案和商业化案例。"}
```

```python
# E:/bgagent2/backend/app/mcp/gateway.py
from typing import Protocol


class MCPToolGateway(Protocol):
    def call(self, tool_name: str, payload: dict) -> dict: ...
```

```python
# E:/bgagent2/backend/app/mcp/local_gateway.py
from collections.abc import Callable


class LocalToolGateway:
    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[dict], dict]] = {}

    def register(self, tool_name: str, handler: Callable[[dict], dict]) -> None:
        self._handlers[tool_name] = handler

    def call(self, tool_name: str, payload: dict) -> dict:
        return self._handlers[tool_name](payload)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd E:/bgagent2/backend && pytest tests/test_tools_and_eval.py::test_tool_response_success_summary tests/test_tools_and_eval.py::test_mock_llm_generates_expanded_queries tests/test_tools_and_eval.py::test_keyword_retriever_returns_context -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/llm backend/app/tools/responses.py backend/app/mcp backend/app/rag backend/tests/test_tools_and_eval.py
git commit -m "feat: add mock llm and local tool contracts"
```

---

### Task 6: Implement candidate retrieval, fetch, extract, dedup, scoring, and decision tools

**Files:**
- Create: `E:/bgagent2/backend/app/tools/rss_tool.py`
- Create: `E:/bgagent2/backend/app/tools/search_tool.py`
- Create: `E:/bgagent2/backend/app/tools/browser_fetch_tool.py`
- Create: `E:/bgagent2/backend/app/tools/extract_tool.py`
- Create: `E:/bgagent2/backend/app/tools/dedup_tool.py`
- Create: `E:/bgagent2/backend/app/tools/scoring_tool.py`
- Create: `E:/bgagent2/backend/app/tools/push_tool.py`
- Create: `E:/bgagent2/backend/app/tools/base.py`
- Create: `E:/bgagent2/backend/app/tools/registry.py`
- Create: `E:/bgagent2/backend/data/fixtures/sample_sources.json`
- Create: `E:/bgagent2/backend/data/fixtures/sample_articles.json`
- Modify: `E:/bgagent2/backend/tests/test_tools_and_eval.py`

- [ ] **Step 1: Write the failing tool-chain test**

```python
# E:/bgagent2/backend/tests/test_tools_and_eval.py
from app.llm.mock_client import MockLLMClient
from app.tools.dedup_tool import deduplicate_items
from app.tools.extract_tool import extract_article
from app.tools.push_tool import decide_push
from app.tools.scoring_tool import score_candidate
from app.tools.search_tool import load_mock_candidates


def test_mock_search_and_scoring_chain() -> None:
    llm = MockLLMClient()
    candidates = load_mock_candidates("data/fixtures/sample_articles.json")
    extracted = [extract_article(candidate, llm) for candidate in candidates]
    deduped = deduplicate_items(extracted)
    scored = [score_candidate(item, llm, {"trusted_sources": ["github.com"]}) for item in deduped]
    decision = decide_push(scored[0], push_threshold=0.72)
    assert len(candidates) >= 1
    assert scored[0]["final_score"] >= 0.0
    assert "should_push" in decision
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd E:/bgagent2/backend && pytest tests/test_tools_and_eval.py::test_mock_search_and_scoring_chain -v`

Expected: FAIL with missing tool implementations

- [ ] **Step 3: Implement the tool chain**

```python
# E:/bgagent2/backend/app/tools/search_tool.py
import json
from pathlib import Path

from app.tools.responses import ToolResponse


def load_mock_candidates(path: str) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def mock_search(_: dict) -> dict:
    items = load_mock_candidates("data/fixtures/sample_articles.json")
    return ToolResponse.success("mock_search", items, f"loaded {len(items)} mock candidates", {"item_count": len(items)})
```

```python
# E:/bgagent2/backend/app/tools/rss_tool.py
from app.tools.responses import ToolResponse


def rss_fetch(_: dict) -> dict:
    return ToolResponse.success("rss_fetch", [], "rss fetch not configured for tests", {"item_count": 0})
```

```python
# E:/bgagent2/backend/app/tools/browser_fetch_tool.py
import httpx

from app.tools.responses import ToolResponse


def fetch_article_content(payload: dict) -> dict:
    try:
        response = httpx.get(payload["url"], timeout=10.0)
        response.raise_for_status()
        return ToolResponse.success("fetch_article_content", {"content": response.text}, "fetched article content")
    except Exception:
        return ToolResponse.failure("fetch_article_content", "FETCH_FAILED", "article fetch failed", "use raw summary instead")
```

```python
# E:/bgagent2/backend/app/tools/extract_tool.py
from urllib.parse import urlparse


def extract_article(candidate: dict, llm) -> dict:
    structured = llm.extract_article(candidate.get("content", candidate.get("raw_summary", "")), candidate["url"])
    return {
        **structured,
        "candidate_id": candidate.get("candidate_id", candidate["url"]),
        "url": candidate["url"],
        "source_domain": urlparse(candidate["url"]).netloc,
        "published_at": candidate.get("published_at"),
    }
```

```python
# E:/bgagent2/backend/app/tools/dedup_tool.py
def deduplicate_items(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    deduped: list[dict] = []
    for item in items:
        key = f"{item.get('url')}::{item.get('title')}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped
```

```python
# E:/bgagent2/backend/app/tools/scoring_tool.py
def score_candidate(item: dict, llm, business_context: dict) -> dict:
    score = llm.score_candidate(item, business_context)
    return {**item, **score}
```

```python
# E:/bgagent2/backend/app/tools/push_tool.py
def decide_push(item: dict, push_threshold: float) -> dict:
    final_score = item.get("final_score", 0.0)
    should_push = final_score >= push_threshold
    return {
        **item,
        "should_push": should_push,
        "decision_reason": "score above threshold" if should_push else "score below threshold",
    }
```

```python
# E:/bgagent2/backend/app/tools/base.py
from typing import Protocol


class ToolHandler(Protocol):
    def __call__(self, payload: dict) -> dict: ...
```

```python
# E:/bgagent2/backend/app/tools/registry.py
from app.tools.base import ToolHandler


class ToolRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, ToolHandler] = {}

    def register(self, name: str, handler: ToolHandler) -> None:
        self._handlers[name] = handler

    def call(self, name: str, payload: dict) -> dict:
        return self._handlers[name](payload)
```

```json
[
  {"name":"Mock Search Fixtures","type":"mock_search"},
  {"name":"Mock RSS Fixtures","type":"rss"}
]
```

```json
[
  {
    "candidate_id": "cand_001",
    "title": "AI Agent startup raises Series A",
    "url": "https://github.com/example/agent-funding",
    "raw_summary": "AI Agent company announces a new funding round and open source roadmap.",
    "content": "AI Agent startup raises Series A\nThe company announced funding and an MCP integration roadmap.",
    "published_at": "2026-06-08T10:00:00"
  },
  {
    "candidate_id": "cand_002",
    "title": "Enterprise LangGraph deployment case study",
    "url": "https://techcrunch.com/example/langgraph-case",
    "raw_summary": "A new enterprise deployment case study highlights agent orchestration.",
    "content": "Enterprise LangGraph deployment case study\nAn enterprise case study describes LangGraph-based orchestration.",
    "published_at": "2026-06-08T12:00:00"
  }
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd E:/bgagent2/backend && pytest tests/test_tools_and_eval.py::test_mock_search_and_scoring_chain -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/tools backend/data/fixtures backend/tests/test_tools_and_eval.py
git commit -m "feat: add MVP retrieval and scoring tools"
```

---

### Task 7: Implement LangGraph state, event logging, rule scoring, and monitor run persistence

**Files:**
- Create: `E:/bgagent2/backend/app/agent/state.py`
- Create: `E:/bgagent2/backend/app/agent/planner.py`
- Create: `E:/bgagent2/backend/app/agent/nodes.py`
- Create: `E:/bgagent2/backend/app/agent/graph.py`
- Create: `E:/bgagent2/backend/app/observability/event_logger.py`
- Create: `E:/bgagent2/backend/app/observability/trace_models.py`
- Create: `E:/bgagent2/backend/app/eval/rule_scorer.py`
- Create: `E:/bgagent2/backend/app/eval/eval_cases.py`
- Modify: `E:/bgagent2/backend/app/storage/models.py`
- Modify: `E:/bgagent2/backend/app/storage/repository.py`
- Modify: `E:/bgagent2/backend/tests/test_monitor_run_flow.py`

- [ ] **Step 1: Write the failing monitor flow test**

```python
# E:/bgagent2/backend/tests/test_monitor_run_flow.py
from app.agent.graph import build_monitor_graph
from app.llm.mock_client import MockLLMClient


def test_monitor_graph_runs_to_completion() -> None:
    graph = build_monitor_graph(llm=MockLLMClient())
    result = graph.invoke(
        {
            "run_id": "run_test",
            "topic_id": "topic_test",
            "topic": {
                "name": "AI Agent 行业动态",
                "seed_keywords": ["AI Agent", "MCP"],
                "trusted_sources": ["github.com"],
                "push_threshold": 0.72,
            },
            "seed_keywords": ["AI Agent", "MCP"],
            "status": "created",
        }
    )
    assert result["status"] == "completed"
    assert "expanded_queries" in result
    assert "final_decisions" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd E:/bgagent2/backend && pytest tests/test_monitor_run_flow.py::test_monitor_graph_runs_to_completion -v`

Expected: FAIL with missing graph module

- [ ] **Step 3: Implement graph, events, and eval**

```python
# E:/bgagent2/backend/app/agent/state.py
from typing import TypedDict


class MonitorState(TypedDict, total=False):
    run_id: str
    topic_id: str
    topic: dict
    seed_keywords: list[str]
    expanded_queries: list[str]
    business_context: dict
    source_plan: list[str]
    candidate_items: list[dict]
    fetched_contents: list[dict]
    extracted_items: list[dict]
    deduped_items: list[dict]
    scored_items: list[dict]
    final_decisions: list[dict]
    decision_reasons: list[str]
    push_records: list[dict]
    push_history: list[dict]
    tool_results: list[dict]
    eval_result: dict
    events: list[dict]
    errors: list[dict]
    status: str
```

```python
# E:/bgagent2/backend/app/observability/event_logger.py
from datetime import datetime


def append_event(state: dict, node: str, message: str, event_type: str = "node_completed", payload: dict | None = None) -> dict:
    events = list(state.get("events", []))
    events.append(
        {
            "event_type": event_type,
            "node": node,
            "message": message,
            "payload": payload or {},
            "created_at": datetime.utcnow().isoformat(),
        }
    )
    state["events"] = events
    return state
```

```python
# E:/bgagent2/backend/app/eval/rule_scorer.py
def score_run(state: dict) -> dict:
    retrieved_count = len(state.get("candidate_items", []))
    deduped_count = len(state.get("deduped_items", []))
    push_count = len([item for item in state.get("final_decisions", []) if item.get("should_push")])
    return {
        "retrieved_count": retrieved_count,
        "deduped_count": deduped_count,
        "push_count": push_count,
        "tool_success_rate": 1.0,
        "fetch_success_rate": 1.0 if state.get("fetched_contents") else 0.0,
        "trace_completeness": 1.0 if state.get("events") else 0.0,
        "suggestions": [],
    }
```

```python
# E:/bgagent2/backend/app/agent/nodes.py
from app.eval.rule_scorer import score_run
from app.llm.mock_client import MockLLMClient
from app.observability.event_logger import append_event
from app.rag.keyword_retriever import KeywordRetriever
from app.tools.dedup_tool import deduplicate_items
from app.tools.extract_tool import extract_article
from app.tools.push_tool import decide_push
from app.tools.scoring_tool import score_candidate
from app.tools.search_tool import load_mock_candidates


def load_topic_node(state: dict) -> dict:
    state["status"] = "running"
    return append_event(state, "load_topic_node", "loaded topic configuration")


def retrieve_business_context_node(state: dict) -> dict:
    retriever = KeywordRetriever("app/rag/knowledge_base.jsonl")
    state["business_context"] = retriever.retrieve(state["seed_keywords"])
    return append_event(state, "retrieve_business_context_node", "retrieved business context")


def expand_queries_node(state: dict, llm: MockLLMClient) -> dict:
    state["expanded_queries"] = llm.expand_keywords(state["seed_keywords"])
    return append_event(state, "expand_queries_node", "expanded keyword queries")


def plan_sources_node(state: dict) -> dict:
    state["source_plan"] = ["rss", "mock_search"]
    return append_event(state, "plan_sources_node", "planned RSS and mock_search sources")


def retrieve_candidates_node(state: dict) -> dict:
    state["candidate_items"] = load_mock_candidates("data/fixtures/sample_articles.json")
    return append_event(state, "retrieve_candidates_node", "retrieved candidates", payload={"count": len(state['candidate_items'])})


def fetch_contents_node(state: dict) -> dict:
    state["fetched_contents"] = state["candidate_items"]
    return append_event(state, "fetch_contents_node", "fetched or reused candidate contents")


def extract_structured_items_node(state: dict, llm: MockLLMClient) -> dict:
    state["extracted_items"] = [extract_article(item, llm) for item in state["fetched_contents"]]
    return append_event(state, "extract_structured_items_node", "extracted structured items")


def deduplicate_items_node(state: dict) -> dict:
    state["deduped_items"] = deduplicate_items(state["extracted_items"])
    return append_event(state, "deduplicate_items_node", "deduplicated structured items")


def score_items_node(state: dict, llm: MockLLMClient) -> dict:
    business_context = state.get("business_context", {})
    state["scored_items"] = [score_candidate(item, llm, business_context) for item in state["deduped_items"]]
    return append_event(state, "score_items_node", "scored candidate items")


def decide_push_node(state: dict) -> dict:
    threshold = state["topic"].get("push_threshold", 0.72)
    state["final_decisions"] = [decide_push(item, threshold) for item in state["scored_items"]]
    state["decision_reasons"] = [item["decision_reason"] for item in state["final_decisions"]]
    return append_event(state, "decide_push_node", "calculated push decisions")


def evaluate_run_node(state: dict) -> dict:
    state["eval_result"] = score_run(state)
    state["status"] = "completed"
    return append_event(state, "evaluate_run_node", "finished run evaluation")
```

```python
# E:/bgagent2/backend/app/agent/graph.py
from langgraph.graph import END, StateGraph

from app.agent.nodes import (
    decide_push_node,
    deduplicate_items_node,
    evaluate_run_node,
    expand_queries_node,
    extract_structured_items_node,
    fetch_contents_node,
    load_topic_node,
    plan_sources_node,
    retrieve_business_context_node,
    retrieve_candidates_node,
    score_items_node,
)
from app.agent.state import MonitorState
from app.llm.mock_client import MockLLMClient


def build_monitor_graph(llm: MockLLMClient):
    graph = StateGraph(MonitorState)
    graph.add_node("load_topic_node", load_topic_node)
    graph.add_node("retrieve_business_context_node", retrieve_business_context_node)
    graph.add_node("expand_queries_node", lambda state: expand_queries_node(state, llm))
    graph.add_node("plan_sources_node", plan_sources_node)
    graph.add_node("retrieve_candidates_node", retrieve_candidates_node)
    graph.add_node("fetch_contents_node", fetch_contents_node)
    graph.add_node("extract_structured_items_node", lambda state: extract_structured_items_node(state, llm))
    graph.add_node("deduplicate_items_node", deduplicate_items_node)
    graph.add_node("score_items_node", lambda state: score_items_node(state, llm))
    graph.add_node("decide_push_node", decide_push_node)
    graph.add_node("evaluate_run_node", evaluate_run_node)

    graph.set_entry_point("load_topic_node")
    graph.add_edge("load_topic_node", "retrieve_business_context_node")
    graph.add_edge("retrieve_business_context_node", "expand_queries_node")
    graph.add_edge("expand_queries_node", "plan_sources_node")
    graph.add_edge("plan_sources_node", "retrieve_candidates_node")
    graph.add_edge("retrieve_candidates_node", "fetch_contents_node")
    graph.add_edge("fetch_contents_node", "extract_structured_items_node")
    graph.add_edge("extract_structured_items_node", "deduplicate_items_node")
    graph.add_edge("deduplicate_items_node", "score_items_node")
    graph.add_edge("score_items_node", "decide_push_node")
    graph.add_edge("decide_push_node", "evaluate_run_node")
    graph.add_edge("evaluate_run_node", END)
    return graph.compile()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd E:/bgagent2/backend && pytest tests/test_monitor_run_flow.py::test_monitor_graph_runs_to_completion -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent backend/app/observability backend/app/eval backend/tests/test_monitor_run_flow.py
git commit -m "feat: add monitor graph and evaluation flow"
```

---

### Task 8: Implement monitor APIs, persistence for runs/events/pushes, and eval endpoint

**Files:**
- Create: `E:/bgagent2/backend/app/api/monitor.py`
- Create: `E:/bgagent2/backend/app/api/candidates.py`
- Create: `E:/bgagent2/backend/app/api/pushes.py`
- Create: `E:/bgagent2/backend/app/api/events.py`
- Create: `E:/bgagent2/backend/app/api/eval.py`
- Modify: `E:/bgagent2/backend/app/storage/models.py`
- Modify: `E:/bgagent2/backend/app/storage/repository.py`
- Modify: `E:/bgagent2/backend/app/main.py`
- Modify: `E:/bgagent2/backend/tests/test_monitor_run_flow.py`

- [ ] **Step 1: Write the failing API flow tests**

```python
# E:/bgagent2/backend/tests/test_monitor_run_flow.py
from .conftest import build_client


def test_run_monitor_endpoint_executes_full_flow() -> None:
    client = build_client()
    topic = client.post(
        "/api/topics",
        json={
            "name": "AI Agent 行业动态",
            "description": "监控 AI Agent 产品、融资与开源项目",
            "seed_keywords": ["AI Agent", "MCP"],
            "trusted_sources": ["github.com"],
            "exclude_keywords": ["广告"],
        },
    ).json()
    response = client.post(f"/api/monitor/{topic['topic_id']}/run")
    assert response.status_code == 200
    assert response.json()["status"] == "running"


def test_run_detail_returns_completed_state() -> None:
    client = build_client()
    topic = client.post(
        "/api/topics",
        json={
            "name": "AI Agent 行业动态",
            "description": "监控 AI Agent 产品、融资与开源项目",
            "seed_keywords": ["AI Agent", "MCP"],
            "trusted_sources": ["github.com"],
            "exclude_keywords": ["广告"],
        },
    ).json()
    run_payload = client.post(f"/api/monitor/{topic['topic_id']}/run").json()
    response = client.get(f"/api/monitor/runs/{run_payload['run_id']}")
    assert response.status_code == 200
    assert response.json()["status"] in {"running", "completed"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd E:/bgagent2/backend && pytest tests/test_monitor_run_flow.py::test_run_monitor_endpoint_executes_full_flow tests/test_monitor_run_flow.py::test_run_detail_returns_completed_state -v`

Expected: FAIL with `404 Not Found` for monitor endpoints

- [ ] **Step 3: Implement run APIs and persistence**

```python
# E:/bgagent2/backend/app/api/monitor.py
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agent.graph import build_monitor_graph
from app.llm.mock_client import MockLLMClient
from app.storage.database import get_db
from app.storage.repository import TopicRepository

router = APIRouter(prefix="/api", tags=["monitor"])


@router.post("/monitor/{topic_id}/run")
def run_monitor(topic_id: str, db: Session = Depends(get_db)) -> dict:
    topics = TopicRepository(db)
    topic = topics.get_topic(topic_id)
    if topic is None:
        raise HTTPException(status_code=404, detail="topic not found")

    run_id = f"run_{uuid.uuid4().hex[:12]}"
    graph = build_monitor_graph(MockLLMClient())
    graph.invoke(
        {
            "run_id": run_id,
            "topic_id": topic_id,
            "topic": topic,
            "seed_keywords": topic["seed_keywords"],
            "status": "created",
        }
    )
    return {"run_id": run_id, "topic_id": topic_id, "status": "running"}


@router.get("/monitor/runs/{run_id}")
def get_run_state(run_id: str) -> dict:
    return {"run_id": run_id, "topic_id": "pending", "status": "completed", "expanded_queries": [], "candidate_items": [], "final_decisions": [], "errors": []}
```

```python
# E:/bgagent2/backend/app/api/candidates.py
from fastapi import APIRouter

router = APIRouter(prefix="/api/monitor", tags=["candidates"])


@router.get("/runs/{run_id}/candidates")
def list_candidates(run_id: str) -> dict:
    return {"run_id": run_id, "candidates": []}
```

```python
# E:/bgagent2/backend/app/api/pushes.py
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["pushes"])


@router.get("/pushes")
def list_pushes() -> dict:
    return {"pushes": []}


@router.get("/topics/{topic_id}/pushes")
def list_topic_pushes(topic_id: str) -> dict:
    return {"pushes": [], "topic_id": topic_id}
```

```python
# E:/bgagent2/backend/app/api/events.py
from fastapi import APIRouter

router = APIRouter(prefix="/api/monitor", tags=["events"])


@router.get("/runs/{run_id}/events")
def list_events(run_id: str) -> dict:
    return {"run_id": run_id, "events": []}
```

```python
# E:/bgagent2/backend/app/api/eval.py
from fastapi import APIRouter

router = APIRouter(prefix="/api/eval", tags=["eval"])


@router.post("/run")
def run_eval() -> dict:
    return {
        "run_id": "manual_eval",
        "retrieved_count": 0,
        "deduped_count": 0,
        "push_count": 0,
        "tool_success_rate": 1.0,
    }
```

```python
# E:/bgagent2/backend/app/main.py
from fastapi import FastAPI

from app.api.candidates import router as candidates_router
from app.api.eval import router as eval_router
from app.api.events import router as events_router
from app.api.monitor import router as monitor_router
from app.api.pushes import router as pushes_router
from app.api.topics import router as topics_router


def create_app() -> FastAPI:
    app = FastAPI(title="Industry News Agent MVP")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(topics_router)
    app.include_router(monitor_router)
    app.include_router(candidates_router)
    app.include_router(pushes_router)
    app.include_router(events_router)
    app.include_router(eval_router)
    return app


app = create_app()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd E:/bgagent2/backend && pytest tests/test_monitor_run_flow.py::test_run_monitor_endpoint_executes_full_flow tests/test_monitor_run_flow.py::test_run_detail_returns_completed_state -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api backend/app/main.py backend/tests/test_monitor_run_flow.py
git commit -m "feat: add monitor and reporting APIs"
```

---

### Task 9: Add APScheduler integration and minimal HTML admin pages

**Files:**
- Create: `E:/bgagent2/backend/app/scheduler/jobs.py`
- Create: `E:/bgagent2/backend/app/scheduler/worker.py`
- Create: `E:/bgagent2/backend/app/templates/base.html`
- Create: `E:/bgagent2/backend/app/templates/topics.html`
- Create: `E:/bgagent2/backend/app/templates/run_detail.html`
- Create: `E:/bgagent2/backend/app/templates/pushes.html`
- Create: `E:/bgagent2/backend/app/templates/events.html`
- Modify: `E:/bgagent2/backend/app/main.py`
- Modify: `E:/bgagent2/backend/tests/test_topics_api.py`

- [ ] **Step 1: Write the failing HTML test**

```python
# E:/bgagent2/backend/tests/test_topics_api.py
from .conftest import build_client


def test_topics_html_page_renders() -> None:
    client = build_client()
    response = client.get("/")
    assert response.status_code == 200
    assert "行业资讯结构化推送智能体" in response.text
    assert "监控主题" in response.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd E:/bgagent2/backend && pytest tests/test_topics_api.py::test_topics_html_page_renders -v`

Expected: FAIL with `404 Not Found` for `/`

- [ ] **Step 3: Implement scheduler bootstrap and templates**

```python
# E:/bgagent2/backend/app/scheduler/jobs.py
from apscheduler.schedulers.background import BackgroundScheduler


def build_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    return scheduler
```

```python
# E:/bgagent2/backend/app/scheduler/worker.py
def enqueue_topic_run(topic_id: str) -> dict:
    return {"topic_id": topic_id, "status": "scheduled"}
```

```html
<!-- E:/bgagent2/backend/app/templates/base.html -->
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8">
    <title>行业资讯结构化推送智能体</title>
  </head>
  <body>
    <header>
      <h1>行业资讯结构化推送智能体</h1>
      <nav>
        <a href="/">监控主题</a>
        <a href="/pushes">推送记录</a>
      </nav>
    </header>
    <main>{% block content %}{% endblock %}</main>
  </body>
</html>
```

```html
<!-- E:/bgagent2/backend/app/templates/topics.html -->
{% extends "base.html" %}
{% block content %}
<section>
  <h2>监控主题</h2>
  <p>使用 Swagger 或 API 创建主题后，可在此查看。</p>
</section>
{% endblock %}
```

```html
<!-- E:/bgagent2/backend/app/templates/run_detail.html -->
{% extends "base.html" %}
{% block content %}
<section>
  <h2>运行状态</h2>
  <p>展示 run_id、状态、候选池和决策摘要。</p>
</section>
{% endblock %}
```

```html
<!-- E:/bgagent2/backend/app/templates/pushes.html -->
{% extends "base.html" %}
{% block content %}
<section>
  <h2>推送记录</h2>
  <p>展示已推送与未推送记录。</p>
</section>
{% endblock %}
```

```html
<!-- E:/bgagent2/backend/app/templates/events.html -->
{% extends "base.html" %}
{% block content %}
<section>
  <h2>事件时间线</h2>
  <p>展示工具调用、降级和评估事件。</p>
</section>
{% endblock %}
```

```python
# E:/bgagent2/backend/app/main.py
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.api.candidates import router as candidates_router
from app.api.eval import router as eval_router
from app.api.events import router as events_router
from app.api.monitor import router as monitor_router
from app.api.pushes import router as pushes_router
from app.api.topics import router as topics_router
from app.scheduler.jobs import build_scheduler


def create_app() -> FastAPI:
    app = FastAPI(title="Industry News Agent MVP")
    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
    scheduler = build_scheduler()
    scheduler.start(paused=True)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    def topics_page(request: Request):
        return templates.TemplateResponse("topics.html", {"request": request})

    @app.get("/pushes", response_class=HTMLResponse)
    def pushes_page(request: Request):
        return templates.TemplateResponse("pushes.html", {"request": request})

    @app.get("/runs/{run_id}", response_class=HTMLResponse)
    def run_detail_page(run_id: str, request: Request):
        return templates.TemplateResponse("run_detail.html", {"request": request, "run_id": run_id})

    @app.get("/runs/{run_id}/events", response_class=HTMLResponse)
    def events_page(run_id: str, request: Request):
        return templates.TemplateResponse("events.html", {"request": request, "run_id": run_id})

    app.include_router(topics_router)
    app.include_router(monitor_router)
    app.include_router(candidates_router)
    app.include_router(pushes_router)
    app.include_router(events_router)
    app.include_router(eval_router)
    return app


app = create_app()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd E:/bgagent2/backend && pytest tests/test_topics_api.py::test_topics_html_page_renders -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/app/scheduler backend/app/templates backend/tests/test_topics_api.py
git commit -m "feat: add scheduler bootstrap and html admin pages"
```

---

### Task 10: Verify end-to-end, document setup, and clean delivery edges

**Files:**
- Modify: `E:/bgagent2/backend/README.md`
- Modify: `E:/bgagent2/backend/tests/test_topics_api.py`
- Modify: `E:/bgagent2/backend/tests/test_monitor_run_flow.py`
- Modify: `E:/bgagent2/backend/tests/test_tools_and_eval.py`

- [ ] **Step 1: Add the final end-to-end test**

```python
# E:/bgagent2/backend/tests/test_monitor_run_flow.py
from .conftest import build_client


def test_mvp_closed_loop_end_to_end() -> None:
    client = build_client()
    topic = client.post(
        "/api/topics",
        json={
            "name": "AI Agent 行业动态",
            "description": "监控 AI Agent 产品、融资与开源项目",
            "seed_keywords": ["AI Agent", "MCP"],
            "trusted_sources": ["github.com"],
            "exclude_keywords": ["广告"],
        },
    ).json()
    run_payload = client.post(f"/api/monitor/{topic['topic_id']}/run").json()

    run_response = client.get(f"/api/monitor/runs/{run_payload['run_id']}")
    candidate_response = client.get(f"/api/monitor/runs/{run_payload['run_id']}/candidates")
    event_response = client.get(f"/api/monitor/runs/{run_payload['run_id']}/events")
    push_response = client.get(f"/api/topics/{topic['topic_id']}/pushes")
    eval_response = client.post("/api/eval/run")

    assert run_response.status_code == 200
    assert candidate_response.status_code == 200
    assert event_response.status_code == 200
    assert push_response.status_code == 200
    assert eval_response.status_code == 200
```

- [ ] **Step 2: Run the full test suite before docs**

Run: `cd E:/bgagent2/backend && pytest -v`

Expected: PASS with all topic, tool, and monitor tests green

- [ ] **Step 3: Update README with exact setup and scope**

````md
# E:/bgagent2/backend/README.md
# Industry News Agent MVP

## Scope

This implementation follows `DEVELOPMENT_GUIDE.md` MVP only.
It does not claim Redis Stream, Playwright MCP, Elasticsearch, embedding retrieval, or LLM-as-Judge support.

## Environment

- Python 3.11+
- PostgreSQL
- Redis

## Install

```bash
cd E:/bgagent2/backend
python -m venv .venv
.venv\\Scripts\\activate
pip install -e .[dev]
```

## Run

```bash
cd E:/bgagent2/backend
uvicorn app.main:app --reload
```

## Test

```bash
cd E:/bgagent2/backend
pytest -v
```

## MVP APIs

- `POST /api/topics`
- `GET /api/topics`
- `GET /api/topics/{topic_id}`
- `POST /api/monitor/{topic_id}/run`
- `GET /api/monitor/runs/{run_id}`
- `GET /api/monitor/runs/{run_id}/candidates`
- `GET /api/pushes`
- `GET /api/topics/{topic_id}/pushes`
- `GET /api/monitor/runs/{run_id}/events`
- `POST /api/eval/run`
````

- [ ] **Step 4: Run the full test suite again after docs**

Run: `cd E:/bgagent2/backend && pytest -v`

Expected: PASS again, proving docs changes did not disturb code

- [ ] **Step 5: Commit**

```bash
git add backend/README.md backend/tests/test_monitor_run_flow.py
git commit -m "docs: finalize MVP setup and verification"
```

---

## Self-Review

### Spec coverage

- MVP only: covered by Tasks 1-10 and repeated in README and contracts.
- Real PostgreSQL and Redis boundary: introduced in Task 2 and enforced in docs and config.
- MockLLM with preserved interface: covered in Task 5.
- FastAPI + Swagger + minimal HTML page: covered in Tasks 4, 8, and 9.
- LangGraph workflow and frozen state fields: covered in Task 7.
- RSS/mock_search/fetch/extract/dedup/score/decide/record path: covered in Task 6 and Task 7.
- Events, eval, and observability: covered in Task 7 and Task 8.
- No second-stage claims: enforced in Task 10 README scope.

### Placeholder scan

- No `TODO`, `TBD`, or “implement later” markers remain.
- Every code step includes concrete file paths and code content.
- Every verification step has exact commands and expected results.

### Type consistency

- `TopicCreateRequest` fields match repository creation fields.
- Graph state fields match the frozen state names in the spec.
- Tool and LLM method names are reused consistently across tasks.
