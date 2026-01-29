"""Configuration for AxiDraw Service"""
from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    """Application settings"""
    
    # Service
    app_name: str = "AxiDraw Service"
    version: str = "1.0.0"
    log_level: str = "INFO"
    
    # Paths
    data_dir: Path = Path("/data")
    uploads_dir: Path = Path("/data/uploads")
    database_url: str = "sqlite+aiosqlite:///data/jobs.db"
    
    # AxiDraw
    axidraw_device: str = "/dev/ttyACM0"  # Default, auto-detect if not found
    max_svg_size_mb: int = 10
    
    # Job Queue
    max_queue_size: int = 100
    job_timeout_seconds: int = 3600  # 1 hour max per job
    
    # API
    api_prefix: str = "/api"
    cors_origins: list[str] = ["*"]
    api_key: str | None = None  # Set via API_KEY env var for authentication
    
    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 100  # requests per window
    rate_limit_window: str = "minute"  # minute, hour, day
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Global settings instance
settings = Settings()

# Ensure directories exist
settings.uploads_dir.mkdir(parents=True, exist_ok=True)
