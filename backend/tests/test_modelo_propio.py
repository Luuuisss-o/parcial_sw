"""
Modelo PROPIO del equipo en el servidor (Gemma 3 1B ajustado, llama.cpp).

En proceso contra la base real, con un llama.cpp falso (MockTransport):
- se le habla con el MISMO prompt del entrenamiento (training/prompt_contract.py);
- edicion: ejecuta las acciones; asesor: las deja como propuesta;
- el proveedor solo se puede elegir si el servidor lo tiene configurado;
- el servidor del modelo descarga versiones nuevas con su token;
- el asesor del celular tambien deja propuestas (proposed_actions).
"""
import json
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from passlib.hash import bcrypt

from app.core.config import settings
from app.core.security import create_access_token
from app.db import SessionLocal
from app.main import app
from app.models.chat import ChatMessage
from app.models.uml import Clase, CollaboratorRole, Diagram, DiagramCollaborator, Relacion
from app.models.user import User
from app.services import trained_model


def _user(db, name):
    u = User(email=f"propio.{uuid.uuid4().hex[:8]}@test.local", name=name, password_hash=bcrypt.hash("x"))
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture()
def configured(monkeypatch):
    monkeypatch.setattr(settings, "LOCAL_MODEL_URL", "http://modelo-propio:8080")
    monkeypatch.setattr(settings, "LOCAL_MODEL_API_KEY", "clave")


@pytest.fixture()
def team():
    db = SessionLocal()
    ana, bruno = _user(db, "Ana"), _user(db, "Bruno")
    d = Diagram(title="Modelo propio", owner_id=ana.id)
    db.add(d)
    db.commit()
    db.add(DiagramCollaborator(diagram_id=d.id, user_id=bruno.id, role=CollaboratorRole.EDITOR))
    db.add_all([Clase(nombre="Cliente", diagram_id=d.id), Clase(nombre="Pedido", diagram_id=d.id)])
    db.commit()
    data = {"diagram_id": str(d.id)}
    for k, u in (("ana", ana), ("bruno", bruno)):
        data[k] = {"id": u.id, "token": create_access_token(u.email)}
    yield data
    db.delete(db.get(Diagram, d.id))
    db.commit()
    for u in (ana, bruno):
        db.delete(db.get(User, u.id))
    db.commit()
    db.close()


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _h(u):
    return {"Authorization": f"Bearer {u['token']}"}


def _fake_llama(monkeypatch, reply: dict | str):
    seen = []

    def handler(request: httpx.Request):
        seen.append({"url": str(request.url), "auth": request.headers.get("authorization"),
                     "body": json.loads(request.content)})
        content = reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)
        return httpx.Response(200, json={"content": content})

    real = httpx.Client
    monkeypatch.setattr(trained_model.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    return seen


def _use_trained(client, team):
    r = client.patch(f"/diagrams/{team['diagram_id']}/ai/settings", json={"provider": "trained"}, headers=_h(team["ana"]))
    assert r.status_code == 200, r.text
    return r.json()


def _ask(client, team, who, text):
    r = client.post(f"/diagrams/{team['diagram_id']}/chat", json={"text": text}, headers=_h(team[who]))
    assert r.status_code == 201, r.text
    db = SessionLocal()
    try:
        return db.query(ChatMessage).filter(ChatMessage.reply_to_id == uuid.UUID(r.json()["id"])).first()
    finally:
        db.close()


def _relations(team):
    db = SessionLocal()
    try:
        return db.query(Relacion).filter(Relacion.diagram_id == uuid.UUID(team["diagram_id"])).count()
    finally:
        db.close()


def test_sin_configurar_no_se_puede_elegir(team, client, monkeypatch):
    monkeypatch.setattr(settings, "LOCAL_MODEL_URL", "")
    r = client.patch(f"/diagrams/{team['diagram_id']}/ai/settings", json={"provider": "trained"}, headers=_h(team["ana"]))
    assert r.status_code == 422
    assert client.get(f"/diagrams/{team['diagram_id']}/ai/settings", headers=_h(team["ana"])).json()["trained_available"] is False


def test_edicion_con_el_prompt_del_entrenamiento(team, client, monkeypatch, configured):
    s = _use_trained(client, team)
    assert s["provider"] == "trained" and s["provider_label"] == settings.LOCAL_MODEL_LABEL and s["trained_available"]
    seen = _fake_llama(monkeypatch, {"say": "Bruno, creé la clase Producto con precio (Double).", "actions": [
        {"tool": "create_class", "args": {"name": "Producto"}},
        {"tool": "add_attribute", "args": {"class_name": "Producto", "name": "precio", "type": "Double", "required": False}},
    ]})
    answer = _ask(client, team, "bruno", "@IA creá la clase Producto con precio")
    # Mismo prompt que el entrenamiento: plantilla de Gemma + prompt de sistema + contexto.
    prompt = seen[0]["body"]["prompt"]
    contract = trained_model.contract()
    assert prompt.startswith("<start_of_turn>user\n" + contract.system_prompt())
    assert "Quien pregunta: Bruno" in prompt and "Consulta actual de Bruno: creá la clase Producto con precio" in prompt
    assert seen[0]["url"].endswith("/completion") and seen[0]["auth"] == "Bearer clave"
    assert answer.ai_model_label == settings.LOCAL_MODEL_LABEL
    assert [a["tool"] for a in answer.actions] == ["create_class", "add_attribute"]
    db = SessionLocal()
    try:
        assert db.query(Clase).filter(Clase.diagram_id == uuid.UUID(team["diagram_id"]), Clase.nombre == "Producto").count() == 1
    finally:
        db.close()


def test_asesor_deja_propuesta_y_aclara_que_no_se_aplico(team, client, monkeypatch, configured):
    """El modelo actual (antes del reentrenamiento) dice "creé la asociación"
    ante una consulta: queda como propuesta y la respuesta lo aclara."""
    _use_trained(client, team)
    _fake_llama(monkeypatch, {"say": "Bruno, creé una asociación entre Cliente (1) y Pedido (1..*).", "actions": [
        {"tool": "create_relation", "args": {"from_class": "Cliente", "to_class": "Pedido", "type": "ASSOCIATION",
                                             "src_multiplicity": "1", "dst_multiplicity": "1..*"}}]})
    answer = _ask(client, team, "bruno", "@IA ¿cómo relacionamos Cliente y Pedido?")
    assert _relations(team) == 0
    assert answer.proposal is not None and answer.proposal.status == "proposed"
    assert "Todavía no se aplicó nada" in answer.content


def test_respuesta_sin_json_no_rompe(team, client, monkeypatch, configured):
    _use_trained(client, team)
    _fake_llama(monkeypatch, "Bruno, una clase abstracta no se puede instanciar.")
    answer = _ask(client, team, "bruno", "@IA ¿qué es una clase abstracta?")
    assert answer.content.startswith("Bruno, una clase abstracta") and answer.proposal is None


def test_servidor_del_modelo_caido(team, client, monkeypatch, configured):
    _use_trained(client, team)

    def handler(request):
        raise httpx.ConnectError("sin conexion")

    real = httpx.Client
    monkeypatch.setattr(trained_model.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    answer = _ask(client, team, "bruno", "@IA creá la clase Producto")
    assert answer.role.value == "ERROR"


def test_token_de_sincronizacion_del_servidor_del_modelo(client, monkeypatch):
    monkeypatch.setattr(settings, "MODEL_SYNC_TOKEN", "token-del-modelo")
    assert client.get("/models/assistant", headers={"X-Model-Sync-Token": "token-del-modelo"}).status_code == 200
    assert client.get("/models/assistant", headers={"X-Model-Sync-Token": "otro"}).status_code == 401
    monkeypatch.setattr(settings, "MODEL_SYNC_TOKEN", "")  # sin token configurado no abre nada
    assert client.get("/models/assistant", headers={"X-Model-Sync-Token": ""}).status_code == 401


def test_asesor_del_celular_deja_propuesta(team, client):
    """El celular responde como asesor y manda lo que propone (no lo aplica)."""
    did = team["diagram_id"]
    q = client.post(f"/diagrams/{did}/chat", json={"text": "@IA ¿cómo relacionamos Cliente y Pedido?",
                                                   "answer_on_device": True}, headers=_h(team["bruno"])).json()
    r = client.post(f"/diagrams/{did}/chat/{q['id']}/answer", headers=_h(team["bruno"]), json={
        "content": "Bruno, conviene Cliente 1 → 0..* Pedido. Lo dejo propuesto.", "ai_mode": "MENTOR",
        "model_label": "Gemma 3 1B personalizado (móvil)",
        "proposed_actions": [{"tool": "create_relation", "args": {"from_class": "Cliente", "to_class": "Pedido",
                                                                  "type": "ASSOCIATION", "src_multiplicity": "1",
                                                                  "dst_multiplicity": "0..*"}}]})
    assert r.status_code == 201, r.text
    assert r.json()["proposal"]["status"] == "proposed"
    assert _relations(team) == 0
