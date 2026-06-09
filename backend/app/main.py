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
