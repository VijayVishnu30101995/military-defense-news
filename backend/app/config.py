from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    app_name: str = "Military & Defense Daily News API"
    app_env: str = "development"
    app_url: str = "http://localhost:8001"

    database_url: str = "sqlite:///./app.db"
    secret_key: str = "development-secret-key-change-me"

    admin_email: str = "admin@defensebrief.com"
    admin_password: str | None = None

    news_timezone: str = "Asia/Kolkata"

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = True
    alert_email_from: str | None = None
    alert_email_to: str | None = None

    # Health alerting configuration
    alert_check_interval_minutes: int = 60
    alert_critical_threshold: int = 3

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()