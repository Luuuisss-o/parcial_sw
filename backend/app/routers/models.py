# app/routers/models.py
"""
Alojamiento del modelo de IA PERSONALIZADO que corre en el celular
(Fase 2, CU-17, modalidad "modelo local en el móvil").

El modelo se entrena fuera del sistema (training/finetune_colab.ipynb, en
Google Colab) y se exporta a GGUF. El servidor solo lo ALOJA: la inferencia
nunca corre aca, corre en el telefono con llama.cpp. La app movil consulta
el manifiesto, y si hay una version nueva la descarga (con reanudacion por
Range si se corta) y verifica el SHA-256 antes de usarla.

  GET /models/assistant            manifiesto (cualquier usuario logueado)
  GET /models/assistant/download   el .gguf (soporta Range)
  PUT /models/assistant            subir una version nueva (solo rol admin)
"""
import hashlib
import json
import logging
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.security import get_current_user
from app.models.user import Role, User
from app.schemas.models import ModelManifest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/models", tags=["models"])

MODEL_FILE = "assistant.gguf"
MANIFEST_FILE = "assistant.json"
MAX_MODEL_BYTES = 4 * 1024 ** 3  # 4 GB: un 1B-3B cuantizado entra holgado
GGUF_MAGIC = b"GGUF"
_VERSION_RE = re.compile(r"^[\w.\-+]{1,64}$")


def _dir() -> Path:
    d = Path(settings.MODELS_DIR)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _read_manifest() -> dict | None:
    p = _dir() / MANIFEST_FILE
    if not p.exists() or not (_dir() / MODEL_FILE).exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


@router.get("/assistant", response_model=ModelManifest)
def get_manifest(me: User = Depends(get_current_user)):
    m = _read_manifest()
    if not m:
        return ModelManifest(available=False)
    return ModelManifest(available=True, download_path="/models/assistant/download", **m)


@router.get("/assistant/download")
def download_model(me: User = Depends(get_current_user)):
    m = _read_manifest()
    if not m:
        raise HTTPException(404, "Todavía no se subió ningún modelo personalizado")
    # FileResponse de Starlette atiende "Range: bytes=..." (206), lo que le
    # permite al celular retomar una descarga de ~800 MB que se corto.
    return FileResponse(
        _dir() / MODEL_FILE,
        media_type="application/octet-stream",
        filename=f"assistant-{m['version']}.gguf",
        headers={"ETag": f'"{m["sha256"]}"', "Cache-Control": "no-cache"},
    )


@router.put("/assistant", response_model=ModelManifest)
async def upload_model(
    file: UploadFile = File(..., description="Modelo GGUF (ej. el exportado por el notebook de Colab)"),
    version: str = Form(..., description="Versión, ej. 2026.11.08-1"),
    base_model: str = Form("", description="Modelo base, ej. google/gemma-3-1b-it"),
    notes: str = Form("", description="Notas del entrenamiento (dataset, épocas...)"),
    me: User = Depends(get_current_user),
):
    if me.role != Role.admin:
        raise HTTPException(403, "Solo un administrador puede publicar el modelo del asistente")
    if not _VERSION_RE.match(version):
        raise HTTPException(422, "Versión inválida (letras, números, '.', '-', '_' o '+', hasta 64)")

    d = _dir()
    sha = hashlib.sha256()
    size = 0
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".part")
    try:
        with os.fdopen(fd, "wb") as out:
            first = True
            while chunk := await file.read(8 * 1024 * 1024):
                if first:
                    if not chunk.startswith(GGUF_MAGIC):
                        raise HTTPException(422, "El archivo no es un modelo GGUF")
                    first = False
                size += len(chunk)
                if size > MAX_MODEL_BYTES:
                    raise HTTPException(413, "El modelo supera el tamaño máximo (4 GB)")
                sha.update(chunk)
                out.write(chunk)
        if size == 0:
            raise HTTPException(422, "El archivo está vacío")
        os.replace(tmp, d / MODEL_FILE)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise

    manifest = {
        "version": version,
        "sha256": sha.hexdigest(),
        "size_bytes": size,
        "base_model": base_model or None,
        "notes": notes or None,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "uploaded_by": me.email,
    }
    (d / MANIFEST_FILE).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"[MODELS] nueva versión {version} ({size} bytes, sha256={manifest['sha256'][:12]}…) por {me.email}")
    return ModelManifest(available=True, download_path="/models/assistant/download", **manifest)
