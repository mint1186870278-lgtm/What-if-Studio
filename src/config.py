"""Configuration management for the application"""

import os
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""

    # Database
    database_url: str = "sqlite:///./projects.db"

    # API Configuration
    debug: bool = os.getenv("DEBUG", "true").lower() == "true"
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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    def ensure_storage_paths(self) -> None:
        """Create storage directories if they don't exist"""
        self.storage_projects_path.mkdir(parents=True, exist_ok=True)
        self.storage_temp_path.mkdir(parents=True, exist_ok=True)


# Global settings instance
settings = Settings()
