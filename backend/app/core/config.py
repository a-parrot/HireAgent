"""Environment configuration, loaded relative to the backend directory."""

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "HireAgent"
    app_host: str = "127.0.0.1"
    app_port: int = Field(default=8000, ge=1, le=65535)
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    db_host: str = "127.0.0.1"
    db_port: int = Field(default=3306, ge=1, le=65535)
    db_name: str = "hireagent"
    db_user: str = "hireagent_app"
    db_password: SecretStr = SecretStr("")
    db_pool_size: int = Field(default=5, ge=1)
    db_max_overflow: int = Field(default=5, ge=0)
    db_connect_timeout: int = Field(default=5, ge=1)
    storage_dir: Path = BACKEND_DIR / "storage"
    upload_max_mb: int = Field(default=20, ge=1, le=200)
    upload_max_files: int = Field(default=250, ge=1, le=1000)
    import_concurrency: int = Field(default=3, ge=1, le=10)
    libreoffice_bin: str = "soffice"
    model_concurrency: int = Field(default=3, ge=1, le=20)
    llm_base_url: str = ""
    llm_provider: str = "openai"
    llm_enable_thinking: bool = False
    llm_max_tokens: int = Field(default=8192, ge=256)
    llm_model: str = ""
    llm_api_key: SecretStr = SecretStr("")
    llm_timeout: int = Field(default=90, ge=1)
    llm_page_chars: int = Field(default=18000, ge=1000)
