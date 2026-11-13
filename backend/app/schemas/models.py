from typing import Optional

from pydantic import BaseModel


class ModelManifest(BaseModel):
    """Modelo de IA personalizado que el celular descarga y ejecuta localmente."""
    available: bool
    version: Optional[str] = None
    sha256: Optional[str] = None
    size_bytes: Optional[int] = None
    base_model: Optional[str] = None
    notes: Optional[str] = None
    uploaded_at: Optional[str] = None
    uploaded_by: Optional[str] = None
    download_path: Optional[str] = None
