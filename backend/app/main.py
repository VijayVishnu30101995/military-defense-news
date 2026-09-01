from fastapi import FastAPI
from sqlalchemy import text

from app.database import engine


app = FastAPI(
    title="Military & Defense Daily News API",
    version="0.1.0",
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