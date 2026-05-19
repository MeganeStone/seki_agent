from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Seki Agent API"
    app_version: str = "0.1.0"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    project_root: Path = Path(__file__).resolve().parents[3]
    data_dir: Path = project_root / "data"
    database_path: Path = data_dir / "db" / "seki_agent.db"
    workspace_dir: Path = data_dir / "workspace"
    diff_work_dir: Path = data_dir / "diff_work"
    spi_work_dir: Path = data_dir / "spi_work"
    translation_work_dir: Path = data_dir / "translation_work"
    legacy_src_dir: Path = project_root / "backend" / "legacy"
    max_upload_size_bytes: int = 600 * 1024 * 1024
    token_secret_key: str = "change-me-in-env"
    access_token_expire_minutes: int = 24 * 60
    rag_api_key: str | None = None
    rag_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    rag_model_name: str = "qwen-plus"
    agent_runner: str = "rule"
    run_live_agent_tests: bool = False
    cors_origins: list[str] = [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="SEKI_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
