from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_SECRET_KEY = "development-secret-key-change-me"


class Settings(BaseSettings):
    app_name: str = "Military & Defense Daily News API"
    app_env: str = "development"
    app_url: str = "http://localhost:8001"

    database_url: str = "sqlite:///./app.db"
    secret_key: str = DEFAULT_SECRET_KEY

    admin_email: str = "admin@defensebrief.com"
    admin_password: str | None = None

    news_timezone: str = "Asia/Kolkata"

    # Minimum defense-relevance score (0-100) a story needs to be shown. Stories below
    # this are still collected and stored, so lowering it brings them back immediately.
    relevance_threshold: int = 30

    # AI key points: set ANTHROPIC_API_KEY to turn them on. Without it the app works as before.
    anthropic_api_key: str | None = None
    key_points_model: str = "claude-haiku-5-5"

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

    @model_validator(mode="after")
    def _require_real_secret_outside_development(self) -> "Settings":
        # The default key is public in this repo, so anyone could forge admin tokens with it.
        if self.app_env != "development" and self.secret_key in ("", DEFAULT_SECRET_KEY):
            raise ValueError("SECRET_KEY must be set when APP_ENV is not 'development'")
        return self


settings = Settings()