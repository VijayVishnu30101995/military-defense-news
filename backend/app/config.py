from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    app_name: str = "Military & Defense Daily News API"
    app_env: str = "development"
    app_url: str = "http://localhost:8001"

    database_url: str
    secret_key: str

    news_timezone: str = "Asia/Kolkata"

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()