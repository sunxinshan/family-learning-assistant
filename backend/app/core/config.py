from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "家庭学习助手"
    app_version: str = "0.1.0"
    environment: Literal["development", "test", "production"] = "development"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./data/dev.db"
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"
    jwt_secret: SecretStr = SecretStr("dev-only-change-me-use-at-least-32-bytes")
    access_token_minutes: int = 30
    refresh_token_days: int = 30
    seed_demo_data: bool = True
    upload_dir: str = "./data/uploads"
    max_upload_bytes: int = 10 * 1024 * 1024
    mastery_threshold: int = 2
    review_intervals_days: list[int] = [1, 3, 7, 14]
    checkpoint_backend: Literal["sqlite", "mysql"] = "sqlite"
    checkpoint_sqlite_path: str = "./data/checkpoints.db"
    checkpoint_url: str | None = None
    prompt_dir: str = "./app/modules/agent/prompts"
    llm_provider: Literal["mock", "openai_compatible"] = "mock"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: SecretStr | None = None
    llm_model: str = "gpt-4.1-mini"
    llm_timeout_seconds: float = 45.0
    cors_origins: list[str] = [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="FLA_",
        extra="ignore",
    )

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        parsed = urlparse(value)
        allowed_schemes = {"sqlite", "sqlite+pysqlite", "mysql", "mysql+pymysql"}
        if parsed.scheme not in allowed_schemes:
            raise ValueError("FLA_DATABASE_URL must use sqlite:/// or mysql+pymysql://")
        return value

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if (
            self.is_production
            and self.jwt_secret.get_secret_value() == "dev-only-change-me-use-at-least-32-bytes"
        ):
            raise ValueError("FLA_JWT_SECRET must be configured in production")
        if self.is_production and self.seed_demo_data:
            raise ValueError("FLA_SEED_DEMO_DATA must be false in production")
        if self.checkpoint_backend == "mysql" and not self.checkpoint_url:
            raise ValueError("FLA_CHECKPOINT_URL is required for MySQL checkpoints")
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
