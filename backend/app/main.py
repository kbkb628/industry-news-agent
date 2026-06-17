from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Event, Thread

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app.api.candidates import router as candidates_router
from app.api.eval import router as eval_router
from app.api.events import router as events_router
from app.api.monitor import router as monitor_router
from app.api.pushes import router as pushes_router
from app.api.topics import get_topic_repository, router as topics_router
from app.core.config import get_settings
from app.scheduler.jobs import TopicSchedulerService, build_scheduler
from app.scheduler.worker import MonitorWorkerLoop, build_run_queue
from app.storage.database import get_session_factory
from app.storage.repository import build_topic_repository


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    scheduler = build_scheduler()
    try:
        settings = get_settings()
    except ValidationError:
        settings = None

    queue = build_run_queue(settings)
    worker_stop_event: Event | None = None
    worker_loop: MonitorWorkerLoop | None = None
    worker_thread: Thread | None = None

    if settings is not None:
        worker_stop_event = Event()
        worker_loop = MonitorWorkerLoop(
            queue=queue,
            session_factory=get_session_factory(settings),
        )
        worker_thread = Thread(
            target=worker_loop.run_forever,
            args=(worker_stop_event,),
            daemon=True,
            name="monitor-worker-loop",
        )

    app.state.run_queue = queue
    app.state.topic_scheduler = TopicSchedulerService(
        scheduler=scheduler,
        queue=queue,
    )

    topic_repository = app.dependency_overrides.get(get_topic_repository)
    if topic_repository is not None:
        topics = topic_repository().list_topics()
        app.state.topic_scheduler.rehydrate_topics(topics)
    elif settings is not None:
        session = get_session_factory(settings)()
        try:
            topics = build_topic_repository(session).list_topics()
            app.state.topic_scheduler.rehydrate_topics(topics)
        finally:
            session.close()

    app.state.monitor_worker_loop = worker_loop
    app.state.monitor_worker_stop_event = worker_stop_event
    app.state.monitor_worker_thread = worker_thread
    if worker_thread is not None:
        worker_thread.start()
    scheduler.start()
    try:
        yield
    finally:
        if worker_stop_event is not None:
            worker_stop_event.set()
        if worker_thread is not None:
            worker_thread.join(timeout=1.0)
        scheduler.shutdown(wait=False)


def create_app() -> FastAPI:
    app = FastAPI(title="Industry News Agent MVP", lifespan=lifespan)
    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    def topics_page(request: Request):
        return templates.TemplateResponse(request, "topics.html")

    @app.get("/pushes", response_class=HTMLResponse)
    def pushes_page(request: Request):
        return templates.TemplateResponse(request, "pushes.html")

    @app.get("/runs/{run_id}", response_class=HTMLResponse)
    def run_detail_page(run_id: str, request: Request):
        return templates.TemplateResponse(
            request,
            "run_detail.html",
            {"request": request, "run_id": run_id},
        )

    @app.get("/runs/{run_id}/events", response_class=HTMLResponse)
    def events_page(run_id: str, request: Request):
        return templates.TemplateResponse(
            request,
            "events.html",
            {"request": request, "run_id": run_id},
        )

    app.include_router(topics_router)
    app.include_router(monitor_router)
    app.include_router(candidates_router)
    app.include_router(pushes_router)
    app.include_router(events_router)
    app.include_router(eval_router)

    return app


app = create_app()
