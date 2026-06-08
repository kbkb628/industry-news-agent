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
