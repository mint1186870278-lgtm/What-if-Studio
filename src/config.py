"""Configuration management for the application"""

import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


class Settings(BaseSettings):
    """Application settings"""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./whatif.db")

    # API Configuration
    debug: bool = True
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    # Storage
    storage_path: str = os.getenv("STORAGE_PATH", "./storage")
    storage_projects_path: Path = Path(storage_path) / "projects"
    storage_temp_path: Path = Path(storage_path) / "temp"

    # Seedance API (placeholder)
    seedance_api_url: str = os.getenv("SEEDANCE_API_URL", "http://localhost:8000")
    seedance_api_key: str = os.getenv("SEEDANCE_API_KEY", "")

    # CORS
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]

    # Server
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))
    frontend_dist_dir: Path = Path(os.getenv("FRONTEND_DIST_DIR", "./web/dist"))
    anet_token: str = os.getenv("ANET_TOKEN", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "")
    openai_model: str = os.getenv("OPENAI_MODEL", os.getenv("AUTOGEN_MODEL", ""))
    siliconflow_api_key: str = os.getenv("SILICONFLOW_API_KEY", "")

    @field_validator("debug", mode="before")
    @classmethod
    def normalize_debug(cls, v):
        if isinstance(v, bool):
            return v
        raw = str(v or "").strip().lower()
        if raw in {"1", "true", "yes", "on", "dev", "debug"}:
            return True
        if raw in {"0", "false", "no", "off", "release", "prod", "production"}:
            return False
        return True

    def ensure_storage_paths(self) -> None:
        """Create storage directories if they don't exist"""
        self.storage_projects_path.mkdir(parents=True, exist_ok=True)
        self.storage_temp_path.mkdir(parents=True, exist_ok=True)

    def validate_openai_env(self) -> None:
        required = {
            "OPENAI_API_KEY": self.openai_api_key,
            "OPENAI_BASE_URL": self.openai_base_url,
            "OPENAI_MODEL": self.openai_model,
        }
        missing = [name for name, value in required.items() if not str(value or "").strip()]
        if missing:
            missing_text = ", ".join(missing)
            raise RuntimeError(
                f"Missing required OpenAI environment variables: {missing_text}. "
                "Please set them in .env before starting the server."
            )


# Global settings instance
settings = Settings()
