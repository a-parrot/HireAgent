"""Environment configuration, loaded relative to the backend directory."""

from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "HireAgent"
    app_host: str = "127.0.0.1"
    app_port: int = Field(default=8000, ge=1, le=65535)
    log_dir: Path = BACKEND_DIR / "logs"
    log_level: str = "INFO"
    log_colorize: bool = True
    log_rotation: str = "20 MB"
    log_retention: str = "14 days"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    auth_cookie_secure: bool = False
    auth_session_hours: int = Field(default=8, ge=1, le=168)
    auth_idle_minutes: int = Field(default=30, ge=1, le=1440)
    auth_docs_enabled: bool = False
    db_host: str = "127.0.0.1"
    db_port: int = Field(default=3306, ge=1, le=65535)
    db_name: str = "hireagent"
    db_user: str = "hireagent_app"
    db_password: SecretStr = SecretStr("")
    db_pool_size: int = Field(default=5, ge=1)
    db_max_overflow: int = Field(default=5, ge=0)
    db_connect_timeout: int = Field(default=5, ge=1)
    startup_lock_wait_seconds: int = Field(default=65, ge=0, le=120)
    runtime_lock_idle_timeout: int = Field(default=60, ge=15, le=3600)
    runtime_lock_heartbeat_interval: float = Field(
        default=10, gt=0, allow_inf_nan=False
    )
    runtime_lock_heartbeat_timeout: float = Field(default=5, gt=0, allow_inf_nan=False)
    storage_dir: Path = BACKEND_DIR / "storage"
    upload_max_mb: int = Field(default=20, ge=1, le=200)
    upload_max_files: int = Field(default=250, ge=1, le=1000)
    import_concurrency: int = Field(default=1, ge=1, le=10)
    model_concurrency: int = Field(default=1, ge=1, le=20)
    external_services_mock: bool = False
    external_action_timeout: float = Field(default=30, gt=0, allow_inf_nan=False)
    llm_base_url: str = ""
    llm_provider: str = "openai"
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_api_key: SecretStr = SecretStr("")
    deepseek_model: str = "deepseek-flash"
    deepseek_max_tokens: int = Field(default=8192, ge=256)
    deepseek_timeout: int = Field(default=300, ge=1)
    llm_enable_thinking: bool = False
    llm_temperature: float = Field(default=0, ge=0, le=2)
    # Same names as the reference knowledge project's llama-server configuration.
    llama_base_url: str = "http://127.0.0.1:8080/v1"
    llama_api_key: SecretStr = SecretStr("")
    llama_max_tokens: int = Field(default=8192, ge=256)
    llm_model_name: str = ""
    llm_max_tokens: int = Field(default=8192, ge=256)
    llm_model: str = ""
    llm_api_key: SecretStr = SecretStr("")
    llm_timeout: int = Field(default=90, ge=1)
    llm_document_chars: int = Field(default=30000, ge=1000)
    llm_page_chars: int = Field(default=18000, ge=1000)

    @model_validator(mode="after")
    def validate_runtime_lock_timing(self):
        if self.llm_provider == "deepseek":
            self.llm_base_url = self.deepseek_base_url
            self.llm_api_key = self.deepseek_api_key
            self.llm_model = self.deepseek_model
            self.llm_max_tokens = self.deepseek_max_tokens
            self.llm_timeout = self.deepseek_timeout
        if self.llm_provider == "llama":
            # Keep the canonical fields consistent for nodes, audit and diagnostics.
            # Cloud credentials must never be forwarded to the local endpoint.
            self.llm_base_url = self.llama_base_url
            self.llm_api_key = self.llama_api_key
            self.llm_model = self.llm_model_name
            self.llm_max_tokens = self.llama_max_tokens
        if (
            self.runtime_lock_heartbeat_interval + self.runtime_lock_heartbeat_timeout
            >= self.runtime_lock_idle_timeout
        ):
            raise ValueError("运行锁心跳间隔加请求超时必须小于锁连接空闲超时")
        return self
