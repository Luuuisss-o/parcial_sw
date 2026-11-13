# app/routers/vision.py
"""
Importar un diagrama a partir de una foto o captura: de clases UML o de
base de datos (tablas con PK/FK, pata de gallo, Chen), ver diagram_vision.py.

Flujo en dos pasos, no uno: el usuario sube la foto, Gemini transcribe lo
que ve y el resultado se le devuelve SIN aplicar a ningun diagrama todavia
(POST /vision/detect). El frontend muestra esa lectura como una vista
previa editable; recien cuando el usuario confirma se crea el diagrama y se
aplican los cambios (POST /vision/apply), reusando DiagramToolExecutor -- el
mismo motor que ya usan el asistente de IA y el import de XMI.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db
from app.core.security import get_current_user
from app.models.uml import Diagram
from app.models.user import User
from app.schemas.vision import VisionApplyIn, VisionApplySummary, VisionDetectResult
from app.services.ai_assistant import describe_error
from app.services.ai_tools import DiagramToolExecutor, ToolError, estimate_h_grid, grid_positions
from app.services.diagram_vision import detect_from_image

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vision", tags=["vision"])

_ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
_MAX_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post("/detect", response_model=VisionDetectResult)
async def detect(
    file: UploadFile,
    me: User = Depends(get_current_user),
):
    content_type = (file.content_type or "").lower()
    if content_type not in _ALLOWED_MIME:
        raise HTTPException(400, "La imagen tiene que ser JPEG, PNG, WEBP o HEIC.")

    content = await file.read()
    if not content:
        raise HTTPException(400, "El archivo esta vacio")
    if len(content) > _MAX_BYTES:
        raise HTTPException(400, "La imagen es demasiado pesada (máximo 10 MB).")

    try:
        result = detect_from_image(content, content_type)
    except RuntimeError as e:
        status = 503 if "mucha demanda" in str(e) else 400
        raise HTTPException(status, str(e))
    except Exception as e:
        logger.error(f"[vision] fallo detectando diagrama: {type(e).__name__}: {e}")
        # Gemini rechaza la imagen en si (danada, en blanco, demasiado chica):
        # es un problema del archivo subido, no del servidor -> 422, no 502.
        if getattr(e, "code", None) == 400 or "INVALID_ARGUMENT" in str(e):
            raise HTTPException(
                422,
                "No se pudo leer la imagen (puede estar dañada, en blanco o ser demasiado chica). "
                "Probá con otra foto del diagrama, nítida y de frente.",
            )
        raise HTTPException(502, describe_error(e))

    if not result.classes:
        raise HTTPException(
            422,
            result.warning or "No se reconoció ninguna clase en la imagen. Probá con una foto más nítida y de frente.",
        )

    return result


@router.post("/apply", response_model=VisionApplySummary)
def apply(
    body: VisionApplyIn,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    if not body.classes:
        raise HTTPException(400, "No hay ninguna clase para crear.")

    diagram = Diagram(title=body.title.strip() or "Diagrama importado", owner_id=me.id)
    db.add(diagram)
    db.commit()
    db.refresh(diagram)

    executor = DiagramToolExecutor(db, diagram, actor_email=me.email)
    summary = VisionApplySummary(diagram_id=str(diagram.id))

    # Posiciones en grilla de 3 columnas (como el import de XMI): un diagrama
    # de base de datos suele traer varias tablas y en una sola fila quedaban
    # fuera de la pantalla. El usuario las reacomoda a gusto después.
    # La fila siguiente empieza debajo de la tarjeta más alta de la anterior
    # (alto estimado por la cantidad de atributos y métodos).
    positions = grid_positions([estimate_h_grid(len(c.attributes), len(c.methods)) for c in body.classes])
    for idx, c in enumerate(body.classes):
        x_grid, y_grid = positions[idx]
        try:
            executor.create_class(name=c.name, x_grid=x_grid, y_grid=y_grid, kind=c.kind)
            summary.classes_created.append(c.name)
        except ToolError as e:
            summary.warnings.append(str(e))
            continue

        for attr in c.attributes:
            try:
                executor.add_attribute(
                    class_name=c.name, name=attr.name, type=attr.type, required=attr.required,
                    visibility=attr.visibility, is_static=attr.is_static, is_derived=attr.is_derived,
                    multiplicity=attr.multiplicity, default_value=attr.default_value,
                )
                summary.attributes_created += 1
            except ToolError as e:
                summary.warnings.append(str(e))

        for m in c.methods:
            try:
                executor.add_method(
                    class_name=c.name, name=m.name, return_type=m.return_type or "void",
                    visibility=m.visibility, is_static=m.is_static, is_abstract=m.is_abstract,
                    params=m.params,
                )
                summary.methods_created += 1
            except ToolError as e:
                summary.warnings.append(str(e))

    for r in body.relations:
        try:
            executor.create_relation(
                from_class=r.from_class,
                to_class=r.to_class,
                type=r.type,
                label=r.label,
                src_multiplicity=r.src_multiplicity,
                dst_multiplicity=r.dst_multiplicity,
                src_role=r.src_role,
                dst_role=r.dst_role,
                src_navigable=r.src_navigable,
                dst_navigable=r.dst_navigable,
            )
            summary.relations_created += 1
        except ToolError as e:
            summary.warnings.append(str(e))
        except ValueError as e:
            # Multiplicidad u otro dato con un formato que el parser no
            # entiende: no debe tirar abajo la creacion de todo el
            # diagrama por una sola relacion con lectura rara de la foto.
            summary.warnings.append(f"No se pudo crear la relación {r.from_class} → {r.to_class}: {e}")

    logger.info(
        f"[vision apply] diagram_id={diagram.id} user={me.id} "
        f"clases={len(summary.classes_created)} atributos={summary.attributes_created} "
        f"metodos={summary.methods_created} "
        f"relaciones={summary.relations_created}"
    )
    return summary
