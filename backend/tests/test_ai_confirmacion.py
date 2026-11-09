"""
CU-04: la IA pide confirmacion antes de una eliminacion con impacto.

Regla del servidor (ai_tools.DiagramToolExecutor), no del criterio del
modelo: borrar una clase con atributos/metodos/relaciones (se pierden en
cascada) o hacer varias eliminaciones en un mismo pedido requiere que el
mensaje del usuario traiga una confirmacion explicita ("confirmo", "si,
eliminala"). Corre en proceso contra la base real, como test_fase2_chat_ia.
"""
import json
import uuid

import httpx
import pytest
from passlib.hash import bcrypt

from app.db import SessionLocal
from app.models.uml import Atributo, Clase, Diagram, Relacion, RelType
from app.models.user import User
from app.services import ai_assistant, llm_providers
from app.services.ai_assistant import Requester
from app.services.ai_tools import CONFIRM_RE, DiagramToolExecutor, ToolError


@pytest.fixture()
def diagram_id():
    db = SessionLocal()
    u = User(email=f"confirm.{uuid.uuid4().hex[:8]}@test.local", name="Ana", password_hash=bcrypt.hash("x"))
    db.add(u)
    db.commit()
    d = Diagram(title="Confirmaciones", owner_id=u.id)
    db.add(d)
    db.commit()
    cliente = Clase(nombre="Cliente", diagram_id=d.id)
    pedido = Clase(nombre="Pedido", diagram_id=d.id)
    vacia = Clase(nombre="Temporal", diagram_id=d.id)
    db.add_all([cliente, pedido, vacia])
    db.commit()
    db.add(Atributo(nombre="email", tipo="String", requerido=False, clase_id=cliente.id))
    db.add(Atributo(nombre="total", tipo="Double", requerido=False, clase_id=pedido.id))
    db.add(Relacion(diagram_id=d.id, origen_id=cliente.id, destino_id=pedido.id, tipo=RelType.ASSOCIATION))
    db.commit()
    did, uid = d.id, u.id
    db.close()
    yield did
    db = SessionLocal()
    db.delete(db.get(Diagram, did))
    db.delete(db.get(User, uid))
    db.commit()
    db.close()


def _class_names(db, did):
    return sorted(c.nombre for c in db.query(Clase).filter(Clase.diagram_id == did))


@pytest.mark.parametrize("text, confirmed", [
    ("@IA confirmo, eliminá Cliente", True),
    ("sí, eliminala", True),
    ("si, borrala nomas", True),
    ("@IA eliminá la clase Cliente", False),
    ("borrá el atributo email", False),
    ("@IA sí, borrala", True),
    ("si eliminás Cliente, ¿qué pasa con Pedido?", False),
])
def test_deteccion_de_confirmacion(text, confirmed):
    assert bool(CONFIRM_RE.search(text)) is confirmed


def test_borrar_clase_con_contenido_sin_confirmar_no_borra(diagram_id):
    db = SessionLocal()
    try:
        ex = DiagramToolExecutor(db, db.get(Diagram, diagram_id), destructive_confirmed=False)
        with pytest.raises(ToolError) as e:
            ex.delete_class("Cliente")
        assert "CONFIRMACION REQUERIDA" in str(e.value)
        assert "1 atributo(s)" in str(e.value) and "1 relacion(es)" in str(e.value)
        assert "Cliente" in _class_names(db, diagram_id)
    finally:
        db.close()


def test_borrar_clase_vacia_o_un_atributo_es_directo(diagram_id):
    db = SessionLocal()
    try:
        ex = DiagramToolExecutor(db, db.get(Diagram, diagram_id), destructive_confirmed=False)
        ex.delete_class("Temporal")
        assert "Temporal" not in _class_names(db, diagram_id)
    finally:
        db.close()


def test_varias_eliminaciones_en_un_pedido_piden_confirmacion(diagram_id):
    db = SessionLocal()
    try:
        ex = DiagramToolExecutor(db, db.get(Diagram, diagram_id), destructive_confirmed=False)
        ex.delete_attribute("Cliente", "email")  # la primera, puntual: se hace
        with pytest.raises(ToolError, match="CONFIRMACION REQUERIDA"):
            ex.delete_attribute("Pedido", "total")
        total = db.query(Atributo).join(Clase).filter(Clase.nombre == "Pedido", Clase.diagram_id == diagram_id).count()
        assert total == 1
    finally:
        db.close()


def test_con_confirmacion_se_borra(diagram_id):
    db = SessionLocal()
    try:
        ex = DiagramToolExecutor(db, db.get(Diagram, diagram_id), destructive_confirmed=True)
        ex.delete_class("Cliente")
        assert "Cliente" not in _class_names(db, diagram_id)
    finally:
        db.close()


def _fake_openai(monkeypatch, script):
    seen = []

    def handler(request: httpx.Request):
        body = json.loads(request.content)
        seen.append(body)
        return httpx.Response(200, json={"choices": [{"message": script(body, len(seen))}]})

    real = httpx.Client
    monkeypatch.setattr(llm_providers.httpx, "Client",
                        lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    return seen


def _delete_cliente_script(body, n):
    if n == 1:
        return {"role": "assistant", "content": None, "tool_calls": [{
            "id": "c1", "type": "function",
            "function": {"name": "delete_class", "arguments": '{"class_name": "Cliente"}'}}]}
    tool_result = body["messages"][-1]["content"]
    if "CONFIRMACION REQUERIDA" in tool_result:
        return {"role": "assistant", "content": "Ana, borrar Cliente elimina su atributo y su relacion. ¿Confirmás?"}
    return {"role": "assistant", "content": "Ana, eliminé la clase Cliente."}


@pytest.mark.parametrize("text, deleted", [
    ("eliminá la clase Cliente", False),
    ("confirmo, eliminá la clase Cliente", True),
])
def test_flujo_completo_del_asistente(diagram_id, monkeypatch, text, deleted):
    _fake_openai(monkeypatch, _delete_cliente_script)
    cfg = llm_providers.ProviderConfig(llm_providers.PROVIDER_OPENAI, "fake", "http://localhost:11434/v1")
    db = SessionLocal()
    try:
        r = ai_assistant.run_command(db, db.get(Diagram, diagram_id), text,
                                     requester=Requester(1, "Ana"), provider=cfg)
        assert ("Cliente" not in _class_names(db, diagram_id)) is deleted
        assert bool(r.actions) is deleted
        assert ("Confirmás" in r.reply) is (not deleted)
    finally:
        db.close()
