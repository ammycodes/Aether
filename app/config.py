import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PORT: int = 8000
    HOST: str = "127.0.0.1"
    DATABASE_URL: str = "sqlite:///./agents.db"
    
    # API Keys (optional for local mock execution)
    GEMINI_API_KEY: str | None = None
    OPENAI_API_KEY: str | None = None
    
    # External Channels
    TELEGRAM_BOT_TOKEN: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

# Instantiate settings
settings = Settings()
