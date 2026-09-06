"""Application configuration loaded from environment variables.

Settings are sourced from `.env` via pydantic-settings. Missing required values
cause fail-fast at startup; never hardcode secrets here.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo layout: backend/app/core/config.py → ../../../.env is the repo-root env file.
_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Strongly-typed application settings."""

    model_config = SettingsConfigDict(
        env_file=str(_REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Database ---
    db_host: str = "localhost"
    db_port: int = 3306
    db_user: str = "food_order"
    db_password: str = ""
    db_name: str = "food_order"
    db_name_test: str = "food_order_test"

    # --- JWT ---
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 10080  # 7 days

    # --- Server ---
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    cors_allow_origins: str = "http://localhost:5173"

    # --- MiniMax LLM (F003 §8.1 — unified model across all 14 cuisine experts) ---
    minimax_api_key: str = ""
    minimax_base_url: str = "https://api.minimaxi.com/v1"
    minimax_model: str = "MiniMax-M3"
    minimax_timeout_seconds: float = 30.0
    minimax_max_retries: int = 2
    minimax_thinking: str = "disabled"  # one of: disabled | enabled | adaptive

    # --- Logging (M2 observability layer) ---
    # log_level: root logger level. Module-specific overrides live in
    # `app/core/logging.py` (e.g. `app.agents.llm` always DEBUG when root
    # is INFO, so prompts/responses can be inspected without changing root).
    log_level: str = "INFO"
    # log_format: "human" (default, color-less stderr with timestamps) or "json"
    # (single-line JSON per record; useful for log shippers).
    log_format: str = "human"
    # log_prompt_debug: gate for full LLM prompt/response bodies in DEBUG logs.
    # Set False in production to never persist raw prompts (privacy / cost).
    log_prompt_debug: bool = True

    @property
    def database_url(self) -> str:
        """Production / dev database URL with utf8mb4 charset."""
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )

    @property
    def test_database_url(self) -> str:
        """Test database URL — used by conftest session fixture."""
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name_test}?charset=utf8mb4"
        )

    @property
    def admin_database_url(self) -> str:
        """Connection to the MySQL server without a default schema — used to
        `CREATE DATABASE` / `DROP DATABASE` for the test schema."""
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/?charset=utf8mb4"
        )

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse CORS origins into a list (comma-separated env)."""
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor — call this from app code."""
    return Settings()
