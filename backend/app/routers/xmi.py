# app/routers/xmi.py
"""
Interoperabilidad con Enterprise Architect via XMI (requisito de la catedra).

- GET  /diagrams/{id}/export-xmi  -> descarga el diagrama como .xmi
- POST /diagrams/{id}/import-xmi  -> sube un .xmi y lo mezcla en el diagrama

El import reusa DiagramToolExecutor (el mismo motor que usa el asistente de
IA): asi cada clase/atributo/relacion creada dispara la misma notificacion
por WebSocket que una edicion manual, y la validacion de nombres duplicados
es una sola implementacion en vez de tres.
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.core.security import get_current_user
from app.models.uml import Clase, Relacion
from app.models.user import User
from app.schemas.xmi import XmiImportSummary
from app.services.ai_tools import DiagramToolExecutor, ToolError
from app.services.xmi import build_xmi, parse_xmi
from ._helpers import get_my_diagram

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/diagrams", tags=["xmi"])


def _mult_str(lo: int, hi: int | None) -> str:
    if hi is None:
        return f"{lo}..*"
    if lo == hi:
        return str(lo)
    return f"{lo}..{hi}"


@router.get("/{diagram_id}/export-xmi")
def export_xmi(
    diagram_id: UUID,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    diagram = get_my_diagram(db, me, diagram_id)
    xml_bytes = build_xmi(diagram)
    filename = f"{diagram.title or 'diagrama'}.xmi".replace(" ", "_")
    return Response(
        content=xml_bytes,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{diagram_id}/import-xmi", response_model=XmiImportSummary)
async def import_xmi(
    diagram_id: UUID,
    file: UploadFile,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    diagram = get_my_diagram(db, me, diagram_id)
    content = await file.read()
    if not content:
        raise HTTPException(400, "El archivo esta vacio")

    parsed = parse_xmi(content)
    if not parsed.classes and not parsed.relations:
        raise HTTPException(
            400,
            "No se encontro ninguna clase ni relacion reconocible en el archivo XMI. "
            + " ".join(parsed.warnings),
        )

    executor = DiagramToolExecutor(db, diagram, actor_email=me.email)
    summary = XmiImportSummary(warnings=list(parsed.warnings))

    # --- Clases + atributos ---
    # Sin esto, create_class() usa x_grid=y_grid=0 para todas: las clases
    # importadas quedan apiladas exactamente una sobre otra y el usuario
    # tiene que reacomodarlas a mano antes de poder ver el diagrama. Una
    # grilla simple (3 columnas, celdas generosas para que quepan clases
    # con varios atributos) alcanza para que el resultado sea usable de
    # entrada; el usuario siempre puede reacomodar despues.
    COLS, COL_W, ROW_H = 3, 18, 16
    for idx, ic in enumerate(parsed.classes):
        try:
            executor.create_class(
                name=ic.name,
                kind=ic.kind,
                x_grid=(idx % COLS) * COL_W,
                y_grid=(idx // COLS) * ROW_H,
            )
            summary.classes_created.append(ic.name)
        except ToolError:
            summary.classes_skipped.append(ic.name)  # ya existia en el diagrama

        for attr in ic.attributes:
            try:
                executor.add_attribute(
                    class_name=ic.name, name=attr.name, type=attr.type, required=attr.required,
                    visibility=attr.visibility, is_static=attr.is_static, is_derived=attr.is_derived,
                    multiplicity=attr.multiplicity, default_value=attr.default_value,
                )
                summary.attributes_created += 1
            except ToolError as e:
                summary.attributes_skipped += 1
                logger.info(f"[XMI import] atributo omitido: {e}")

        for method in ic.methods:
            try:
                executor.add_method(
                    class_name=ic.name, name=method.name, return_type=method.return_type,
                    visibility=method.visibility, is_static=method.is_static,
                    is_abstract=method.is_abstract, params=method.params,
                )
                summary.methods_created += 1
            except ToolError as e:
                summary.methods_skipped += 1
                logger.info(f"[XMI import] metodo omitido: {e}")

    # --- Relaciones ---
    # DiagramToolExecutor.create_relation no chequea duplicados a proposito:
    # el asistente de IA puede querer una segunda relacion (distinto tipo)
    # entre las mismas dos clases, y eso es UML valido. Pero reimportar el
    # mismo XMI dos veces sobre el mismo diagrama tiene que ser idempotente,
    # asi que ese chequeo va aca, especifico del import.
    existentes = set()
    for r in db.query(Relacion).filter(Relacion.diagram_id == diagram.id).all():
        existentes.add((r.origen.nombre.lower(), r.destino.nombre.lower(), r.tipo.value))

    for ir in parsed.relations:
        key = (ir.from_name.strip().lower(), ir.to_name.strip().lower(), ir.type)
        if key in existentes:
            summary.relations_skipped += 1
            continue
        try:
            executor.create_relation(
                from_class=ir.from_name,
                to_class=ir.to_name,
                type=ir.type,
                label=ir.label,
                src_multiplicity=_mult_str(ir.src_mult_min, ir.src_mult_max),
                dst_multiplicity=_mult_str(ir.dst_mult_min, ir.dst_mult_max),
                es_clase_asociacion=ir.es_clase_asociacion,
                src_role=ir.src_role,
                dst_role=ir.dst_role,
                src_navigable=ir.src_navigable,
                dst_navigable=ir.dst_navigable,
            )
            summary.relations_created += 1
        except ToolError as e:
            summary.relations_skipped += 1
            summary.warnings.append(str(e))

    # --- Reposicionar clases de asociacion recien creadas ---
    # La grilla generica de arriba no sabe nada de relaciones todavia (las
    # clases se crean antes), asi que una clase intermedia (es_clase_asociacion)
    # termina en cualquier celda, lejos de las 2 clases que conecta -- las
    # 2 lineas punteadas de la geometria en T (ver ConnectionLayer.jsx)
    # terminan cruzando medio diagrama. Una vez que las relaciones ya
    # existen, se puede detectar que clase es intermedia de que par y
    # moverla al punto medio real entre esas dos, en celdas de grilla.
    nombres_creados = {n.lower() for n in summary.classes_created}
    if nombres_creados:
        por_id = {c.id: c for c in db.query(Clase).filter(Clase.diagram_id == diagram.id).all()}

        flagged = [
            r for r in db.query(Relacion)
            .filter(Relacion.diagram_id == diagram.id)
            .filter(Relacion.es_clase_asociacion.is_(True))
            .all()
        ]
        by_intermedia: dict[str, list] = {}
        for r in flagged:
            for lado in (r.origen_id, r.destino_id):
                by_intermedia.setdefault(lado, []).append(r)

        for clase_id, rels in by_intermedia.items():
            if len(rels) != 2:
                continue
            r1, r2 = rels
            if r1.id == r2.id:
                continue
            other1 = r1.destino_id if r1.origen_id == clase_id else r1.origen_id
            other2 = r2.destino_id if r2.origen_id == clase_id else r2.origen_id
            if not other1 or not other2 or other1 == other2 or other1 == clase_id or other2 == clase_id:
                continue
            intermedia = por_id.get(clase_id)
            clase_a = por_id.get(other1)
            clase_b = por_id.get(other2)
            if not intermedia or not clase_a or not clase_b:
                continue
            if intermedia.nombre.lower() not in nombres_creados:
                continue  # solo reposicionar clases que este import creo, no mover las que ya estaban
            try:
                executor.move_class(
                    class_name=intermedia.nombre,
                    x_grid=round((clase_a.x_grid + clase_b.x_grid) / 2),
                    y_grid=round((clase_a.y_grid + clase_b.y_grid) / 2) + 4,
                )
            except ToolError as e:
                logger.info(f"[XMI import] no se pudo reposicionar '{intermedia.nombre}': {e}")

    logger.info(
        f"[XMI import] diagram_id={diagram_id} "
        f"clases={len(summary.classes_created)} atributos={summary.attributes_created} "
        f"relaciones={summary.relations_created}"
    )
    return summary
