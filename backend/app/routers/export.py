
# app/routes/export.py
import os, sys, zipfile
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from uuid import UUID

from app.db import get_db
from app.models.uml import Diagram

# Paths
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
sys.path.append(PROJECT_ROOT)

EXPORT_DIR = os.path.join(PROJECT_ROOT, "exporters", "json")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "exporters", "output", "generated_project_test")
os.makedirs(EXPORT_DIR, exist_ok=True)

# Importar generadores
from exporters.generators.uml_to_json import export_diagram_to_json
from exporters.generators.validator import UMLValidationError
from exporters.generators.project_builder import build_project

router = APIRouter(prefix="/diagrams", tags=["export"])


def build_diagram_dict(diagram: Diagram) -> dict:
    return {
        "id": str(diagram.id),
        "title": diagram.title,
        "classes": [
            {
                "id": str(c.id),
                "name": c.nombre,
                "attributes": [
                    {"name": a.nombre, "type": a.tipo, "required": a.requerido}
                    for a in c.atributos
                ],
                "methods": [
                    {"name": m.nombre, "return_type": m.tipo_retorno}
                    for m in c.metodos
                ],
            }
            for c in diagram.classes
        ],
        "relations": [
            {
                "from": r.origen.nombre,
                "from_id": str(r.origen_id),
                "to": r.destino.nombre,
                "to_id": str(r.destino_id),
                "type": r.tipo.value,
                "from_min": r.mult_origen_min,
                "from_max": r.mult_origen_max,
                "to_min": r.mult_destino_min,
                "to_max": r.mult_destino_max,
                "label": r.etiqueta or "",
                "role_from": r.origen.nombre.lower(),
                "role_to": r.destino.nombre.lower(),
            }
            for r in diagram.relations
        ],
    }


def zip_generated_project(output_dir: str, zip_path: str):
    if os.path.exists(zip_path):
        os.remove(zip_path)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(output_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, output_dir)
                zipf.write(file_path, arcname)
    return zip_path

@router.post("/{diagram_id}/export-download")
def export_and_download(diagram_id: UUID, db: Session = Depends(get_db)):
    diagram = db.query(Diagram).filter(Diagram.id == diagram_id).first()
    if not diagram:
        raise HTTPException(404, "Diagrama no encontrado")

    json_path = os.path.join(EXPORT_DIR, f"diagram_{diagram_id}.json")
    output_dir = os.path.join(PROJECT_ROOT, "exporters", "output", f"generated_project_{diagram_id}")
    zip_path = os.path.join(EXPORT_DIR, f"generated_project_{diagram_id}.zip")

    try:
        # 1) Guardar JSON UML
        diagram_dict = build_diagram_dict(diagram)
        export_diagram_to_json(diagram_dict, json_path)

        # 2) Construir proyecto en carpeta única
        build_project(json_path, output_dir)

        # 3) Comprimir en ZIP
        zip_generated_project(output_dir, zip_path)

        # 4) Descargar directamente el ZIP
        return FileResponse(
            zip_path,
            media_type="application/zip",
            filename=f"generated_project_{diagram_id}.zip"
        )

    except UMLValidationError as e:
        raise HTTPException(status_code=400, detail=f"Error de validación UML: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno: {e}")
