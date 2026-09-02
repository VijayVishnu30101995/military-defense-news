from fastapi import FastAPI
from sqlalchemy import text

from app.api.v1.auth import router as auth_router
from app.database import engine


app = FastAPI(
    title="Military & Defense Daily News API",
    version="0.1.0",
)


app.include_router(
    auth_router,
    prefix="/api/v1",
)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "military-defense-news-api",
    }


@app.get("/ready")
def ready():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))

    return {
        "status": "ready",
        "database": "ok",
    }