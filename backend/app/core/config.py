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
    # Proveedor de IA por defecto del servidor (Fase 2, CU-17). Vacio = Gemini.
    # "openai_compatible" para un modelo local (Ollama, LM Studio, Colab...).
    AI_PROVIDER: str = ""
    AI_BASE_URL: str = ""
    AI_MODEL: str = ""
    AI_API_KEY: str = ""
    # Donde se aloja el modelo personalizado que descarga el celular.
    MODELS_DIR: str = "data/models"
    # Modelo PROPIO del equipo servido con llama.cpp en otra instancia
    # (deploy/model_server). Vacio = no disponible como proveedor.
    LOCAL_MODEL_URL: str = ""
    LOCAL_MODEL_API_KEY: str = ""
    # Certificado (PEM en base64) del servidor del modelo: con https:// el
    # backend confia SOLO en el (pinning). Lo imprime setup_model_server.sh.
    LOCAL_MODEL_CERT: str = ""
    LOCAL_MODEL_LABEL: str = "Gemma 3 1B propio del equipo"
    # Token con el que el servidor del modelo descarga las versiones nuevas
    # (GET /models/assistant[/download]) sin una cuenta de usuario.
    MODEL_SYNC_TOKEN: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

ALLOWED_ORIGINS: List[str] = [
    o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()
]