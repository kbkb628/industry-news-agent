from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
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


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    scheduler = build_scheduler()
    scheduler.start(paused=True)
    try:
        yield
    finally:
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
