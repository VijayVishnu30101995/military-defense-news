from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1.articles import router as articles_router
from app.api.v1.auth import router as auth_router
from app.api.v1.health import router as health_router
from app.api.v1.sources import router as sources_router
from app.api.v1.users import router as users_router
from app.api.dependencies import get_current_user
from app.core.reference_data import ensure_reference_data
from app.database import SessionLocal, engine
from app.models.user import User
from app.schemas.auth import UserResponse
from app.services.scheduler import start_collection_scheduler, stop_collection_scheduler


@asynccontextmanager
async def lifespan(_app: FastAPI):
    with SessionLocal() as db:
        ensure_reference_data(db)

    start_collection_scheduler()
    try:
        yield
    finally:
        stop_collection_scheduler()


app = FastAPI(
    title="Military & Defense Daily News API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


app.include_router(
    auth_router,
    prefix="/api/v1",
)


app.include_router(
    sources_router,
    prefix="/api/v1",
)

app.include_router(
    articles_router,
    prefix="/api/v1",
)

app.include_router(
    health_router,
    prefix="/api/v1",
)

app.include_router(
    users_router,
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


@app.get("/api/v1/me", response_model=UserResponse)
def get_me_alias(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        display_name=current_user.display_name,
        role=current_user.role,
        is_active=current_user.is_active,
    )


@app.post("/api/v1/logout", status_code=status.HTTP_200_OK)
def logout_alias() -> dict[str, str]:
    return {"detail": "Logged out successfully"}