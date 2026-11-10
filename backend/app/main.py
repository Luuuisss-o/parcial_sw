# backend/app/main.py
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import ALLOWED_ORIGINS, settings
from app.routers import auth as auth_router
from app.routers import diagramas, classes, atributos, metodo, relacion, realtime
from app.routers import classes as classes_router
from app.routers import export
from app.routers import ai
from app.routers import xmi
from app.routers import vision
from app.routers import voice
from app.routers import chat
from app.routers import models as models_router
from app.ws_manager import ws_manager
app = FastAPI(title="UML AI Tool API")
# Sin emoji a propósito: con --reload, el proceso worker que crea uvicorn en
# Windows no siempre hereda una consola UTF-8, y un emoji en un print de
# arranque tira UnicodeEncodeError con la codificación cp1252 por defecto,
# lo que directamente impide que el backend levante.
print("ALLOWED_ORIGINS:", ALLOWED_ORIGINS)


@app.on_event("startup")
async def _capture_main_loop():
    # Necesario para que las notificaciones realtime disparadas desde
    # endpoints sincronos (ej. el asistente de IA) puedan programarse en
    # el loop correcto via run_coroutine_threadsafe.
    ws_manager.main_loop = asyncio.get_running_loop()
    # Consultas a la IA que quedaron colgadas por un reinicio: se cierran y
    # se avisa en el chat (segundo parcial, confiabilidad del asesor).
    from app.services.chat_service import recover_interrupted_questions
    try:
        recover_interrupted_questions()
    except Exception as e:  # la base puede no estar lista en algun arranque de prueba
        print(f"[startup] no se pudieron revisar consultas interrumpidas: {e}")
cors_origins = ["*"] if settings.DEBUG else ALLOWED_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

@app.get("/health")
def health():
    return {"ok": True}
# 🔹 Ruta raíz (útil en navegador/Render)
@app.get("/")
def root():
    return {"status": "ok", "message": "Backend is running 🚀"}
app.include_router(auth_router.router)

app.include_router(diagramas.router)
app.include_router(classes.router)
app.include_router(atributos.router)
app.include_router(metodo.router)
app.include_router(relacion.router)
app.include_router(export.router)
app.include_router(ai.router)
app.include_router(xmi.router)
app.include_router(vision.router)
app.include_router(voice.router)
app.include_router(chat.router)
app.include_router(models_router.router)
# Router WebSocket (colaboración en tiempo real)
app.include_router(realtime.router)