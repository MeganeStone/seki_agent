from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    """后端统一配置对象。

    所有 `SEKI_` 前缀的环境变量都会映射到这里。业务代码只依赖 Settings，
    不直接到处读取 `.env`，这样测试时可以更容易替换配置，也便于之后迁移到
    Docker、K8s 或配置中心。
    """
    app_name: str = "Seki Agent API"
    app_version: str = "0.1.0"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    project_root: Path = Path(__file__).resolve().parents[3]
    data_dir: Path = project_root / "data"
    # PostgreSQL 连接串；本地默认连开发库，Docker/生产通过 SEKI_DATABASE_URL 覆盖。
    database_url: str = "postgresql://postgres:postgres@127.0.0.1:5432/seki_agent"
    workspace_dir: Path = data_dir / "workspace"
    skills_dir: Path = data_dir / "skills"
    diff_work_dir: Path = data_dir / "diff_work"
    spi_work_dir: Path = data_dir / "spi_work"
    translation_work_dir: Path = data_dir / "translation_work"
    legacy_src_dir: Path = project_root / "backend" / "legacy"
    max_upload_size_bytes: int = 600 * 1024 * 1024
    token_secret_key: str = "change-me-in-env"
    access_token_expire_minutes: int = 24 * 60
    rag_api_key: str | None = None
    rag_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    rag_model_name: str = "qwen3.7-max"
    web_search_api_key: str | None = None
    web_search_api_url: str = "https://open.feedcoopapi.com/search_api/web_search"
    web_search_timeout_seconds: float = 30.0
    web_search_max_summary_chars: int = 4000
    task_executor: str = "sync"
    task_executor_max_workers: int = 3
    # Celery broker；本机开发指向 Memurai/Redis，Docker 指向 redis 服务。
    celery_broker_url: str = "redis://127.0.0.1:6379/0"
    # 测试/无 Redis 环境可置 true，任务在进程内同步执行。
    celery_task_always_eager: bool = False
    code_agent_allowed_roots: list[Path] | None = None
    code_agent_max_read_bytes: int = 1024 * 1024
    code_agent_max_write_bytes: int = 1024 * 1024
    code_agent_allowed_command_prefixes: list[str] = []
    code_agent_confirmed_command_prefixes: list[str] = []
    run_live_agent_tests: bool = False
    # 结构化日志：json 输出单行 JSON，console 为本地可读格式。
    log_level: str = "INFO"
    log_format: str = "json"
    # 单个会话的 token 预算基数；达到 N 倍基数时需要用户确认才能继续，0 表示不限制。
    max_conversation_tokens: int = 200_000
    cors_origins: list[str] = [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://192.168.144.22:5173",  # 支持局域网 IP 的 CORS 白名单
        "http://192.168.144.22:8000",  # 支持局域网 IP 的 CORS 白名单
    ]

    # 如果需要支持任意局域网 IP + 任意端口，使用正则表达式并在中间件中传给 `allow_origin_regex`。
    cors_origin_regex: str | None = r"^http://192\.168\.\d{1,3}\.\d{1,3}:\d+$"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="SEKI_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """返回缓存后的配置实例。

    配置读取会解析路径、列表和布尔值，缓存可以避免每次请求重复解析环境变量。
    测试如需替换配置，可清理这个 cache 后重新构造。
    """
    return Settings()
