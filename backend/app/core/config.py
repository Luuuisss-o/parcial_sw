#app/core/config.py
from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    DB_URL: str
    JWT_SECRET: str
    JWT_ALG: str = "HS256"
    ACCESS_EXPIRE_MIN: int = 480
    REFRESH_EXPIRE_DAYS: int = 14
    CORS_ORIGINS: str = ""
    DEBUG: bool = False
    GEMINI_API_KEY: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

ALLOWED_ORIGINS: List[str] = [
    o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()
]