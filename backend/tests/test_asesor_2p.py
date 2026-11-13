"""
Segundo parcial: la IA como asesor (desarrollador senior) del equipo.

Corre EN PROCESO (TestClient) contra la base real, como test_fase2_chat_ia,
con un modelo falso de API compatible con OpenAI para controlar exactamente
que responde/propone la IA:

- CU-05/06: el asesor PROPONE cambios estructurados; el diagrama no cambia.
- CU-07: aceptar aplica una sola vez, por el servicio de operaciones; si las
  clases involucradas cambiaron, la propuesta queda "stale"; permisos.
- CU-08: asesor desactivable, propuestas desactivables, modo a demanda.
- Confiabilidad: una consulta en curso por persona, recuperacion tras un
  reinicio, caida del proveedor sin romper el chat.
- CU-04: aislamiento entre diagramas y contexto con multiplicidades.
"""
import json
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from passlib.hash import bcrypt

from app.core.security import create_access_token
from app.db import SessionLocal
from app.main import app
from app.models.chat import AiProposal, ChatMessage, ChatRole
from app.models.uml import (Atributo, Clase, CollaboratorRole, Diagram, DiagramCollaborator, Relacion,
                            RelType)
from app.models.user import User
from app.services import chat_service, llm_providers


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _user(db, name):
    u = User(email=f"asesor.{uuid.uuid4().hex[:8]}@test.local", name=name, password_hash=bcrypt.hash("x"))
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture()
def team():
    """Diagrama de Ana (dueña) con Bruno y Dani como colaboradores, las
    clases Cliente y Pedido, y el proveedor de IA apuntando al modelo falso."""
    db = SessionLocal()
    ana, bruno, dani = _user(db, "Ana"), _user(db, "Bruno"), _user(db, "Dani")
    d = Diagram(title="Asesor 2P", owner_id=ana.id, ai_provider=llm_providers.PROVIDER_OPENAI,
                ai_base_url="http://modelo-falso/v1", ai_model="falso")
    db.add(d)
    db.commit()
    for u in (bruno, dani):
        db.add(DiagramCollaborator(diagram_id=d.id, user_id=u.id, role=CollaboratorRole.EDITOR))
    cliente, pedido = Clase(nombre="Cliente", diagram_id=d.id), Clase(nombre="Pedido", diagram_id=d.id)
    db.add_all([cliente, pedido])
    db.commit()
    db.add(Atributo(nombre="nombre", tipo="String", requerido=True, clase_id=cliente.id))
    db.commit()
    data = {"diagram_id": str(d.id)}
    for key, u in (("ana", ana), ("bruno", bruno), ("dani", dani)):
        data[key] = {"id": u.id, "name": u.name, "token": create_access_token(u.email)}
    yield data
    db.delete(db.get(Diagram, d.id))
    db.commit()
    for u in (ana, bruno, dani):
        db.delete(db.get(User, u.id))
    db.commit()
    db.close()


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _h(user):
    return {"Authorization": f"Bearer {user['token']}"}


def _fake_model(monkeypatch, script):
    """Servidor falso OpenAI-compatible: `script(body, n)` devuelve el mensaje."""
    seen = []

    def handler(request: httpx.Request):
        body = json.loads(request.content)
        seen.append(body)
        return httpx.Response(200, json={"choices": [{"message": script(body, len(seen))}]})

    real = httpx.Client
    monkeypatch.setattr(llm_providers.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    return seen


def _propose(ops, summary="Relacionar Cliente con Pedido de uno a muchos"):
    return {"role": "assistant", "content": None, "tool_calls": [{
        "id": "p1", "type": "function",
        "function": {"name": "propose_changes", "arguments": json.dumps({"summary": summary, "operations": ops})}}]}


REL_OPS = [{"tool": "create_relation", "args": {"from_class": "Cliente", "to_class": "Pedido", "type": "ASSOCIATION",
                                               "src_multiplicity": "1", "dst_multiplicity": "0..*"}}]


def _advisor_script(ops=REL_OPS):
    def script(body, n):
        if n == 1:
            return _propose(ops)
        return {"role": "assistant", "content": "Bruno, conviene Cliente 1 — 0..* Pedido. Te lo dejé propuesto."}
    return script


def _ask(client, team, who, text):
    r = client.post(f"/diagrams/{team['diagram_id']}/chat", json={"text": text}, headers=_h(team[who]))
    assert r.status_code == 201, r.text
    return r.json()


def _answer_to(team, question_id):
    db = SessionLocal()
    try:
        return db.query(ChatMessage).filter(ChatMessage.reply_to_id == uuid.UUID(question_id)).order_by(ChatMessage.seq).first()
    finally:
        db.close()


def _relations(team):
    db = SessionLocal()
    try:
        return [(r.origen.nombre, r.destino.nombre, r.tipo.value)
                for r in db.query(Relacion).filter(Relacion.diagram_id == uuid.UUID(team["diagram_id"]))]
    finally:
        db.close()


# ---------------------------------------------------------------------------
# CU-05 / CU-06: el asesor propone, no modifica
# ---------------------------------------------------------------------------
def test_asesor_propone_sin_modificar_el_diagrama(team, client, monkeypatch):
    seen = _fake_model(monkeypatch, _advisor_script())
    q = _ask(client, team, "bruno", "@IA ¿cómo relacionamos Cliente y Pedido?")
    # El asesor solo recibe la herramienta de proponer (ninguna que edite).
    assert [t["function"]["name"] for t in seen[0]["tools"]] == ["propose_changes"]
    assert _relations(team) == []  # nada se aplico

    hist = client.get(f"/diagrams/{team['diagram_id']}/chat", headers=_h(team["dani"])).json()["items"]
    answer = next(m for m in hist if m["reply_to_id"] == q["id"])
    assert answer["addressed_to_name"] == "Bruno" and answer["ai_mode"] == "MENTOR"
    p = answer["proposal"]
    assert p["status"] == "proposed" and p["requested_by_name"] == "Bruno"
    assert p["changes"] == ["Relacionar Cliente → Pedido: ASSOCIATION (1 → 0..*)"]
    question = next(m for m in hist if m["id"] == q["id"])
    assert question["ai_status"] == "completed"


def test_propuesta_invalida_se_devuelve_al_modelo_para_corregir(team, client, monkeypatch):
    bad = [{"tool": "create_relation", "args": {"from_class": "Cliente", "to_class": "Factura", "type": "ASSOCIATION"}}]

    def script(body, n):
        if n == 1:
            return _propose(bad)
        if n == 2:
            assert "Factura" in body["messages"][-1]["content"]  # recibe el error
            return _propose(REL_OPS)
        return {"role": "assistant", "content": "Bruno, corregido: te lo dejé propuesto."}

    _fake_model(monkeypatch, script)
    q = _ask(client, team, "bruno", "@IA ¿cómo relacionamos Cliente y Pedido?")
    p = _answer_to(team, q["id"]).proposal
    assert p is not None and p.operations[0]["args"]["to_class"] == "Pedido"


def test_herramientas_de_edicion_no_se_aceptan_en_modo_asesor(team, client, monkeypatch):
    def script(body, n):
        if n == 1:
            return {"role": "assistant", "content": None, "tool_calls": [{"id": "x", "type": "function",
                    "function": {"name": "delete_class", "arguments": '{"class_name": "Cliente"}'}}]}
        return {"role": "assistant", "content": "Bruno, no puedo borrar desde aquí."}

    _fake_model(monkeypatch, script)
    _ask(client, team, "bruno", "@IA ¿qué opinás de la clase Cliente?")
    db = SessionLocal()
    try:
        assert db.query(Clase).filter(Clase.diagram_id == uuid.UUID(team["diagram_id"]), Clase.nombre == "Cliente").count() == 1
    finally:
        db.close()


# ---------------------------------------------------------------------------
# CU-07: aceptar / rechazar
# ---------------------------------------------------------------------------
def _proposal_id(client, team, monkeypatch, who="bruno"):
    _fake_model(monkeypatch, _advisor_script())
    q = _ask(client, team, who, "@IA ¿cómo relacionamos Cliente y Pedido?")
    return str(_answer_to(team, q["id"]).proposal.id)


def test_aceptar_aplica_una_sola_vez_y_queda_registrado(team, client, monkeypatch):
    pid = _proposal_id(client, team, monkeypatch)
    url = f"/diagrams/{team['diagram_id']}/ai/proposals/{pid}"
    with client.websocket_connect(f"/diagrams/{team['diagram_id']}/ws?token={team['dani']['token']}") as ws:
        r = client.post(url + "/accept", headers=_h(team["bruno"]))
        assert r.status_code == 200 and r.json()["status"] == "applied", r.text
        events = {}
        for _ in range(40):
            m = ws.receive_json()
            events[m["event"]] = m["data"]
            if {"relation.created", "ai.proposal"} <= events.keys():
                break
        assert events["ai.proposal"]["status"] == "applied"  # Dani lo ve en vivo
    assert _relations(team) == [("Cliente", "Pedido", "ASSOCIATION")]
    assert client.post(url + "/accept", headers=_h(team["ana"])).status_code == 409  # no se aplica dos veces
    assert _relations(team) == [("Cliente", "Pedido", "ASSOCIATION")]
    hist = client.get(f"/diagrams/{team['diagram_id']}/chat", headers=_h(team["ana"])).json()["items"]
    assert any(m["ai_mode"] == "PROPOSAL" and m["content"].startswith("Bruno aplicó la propuesta") for m in hist)


def test_solo_quien_pregunto_o_la_duena_deciden(team, client, monkeypatch):
    pid = _proposal_id(client, team, monkeypatch)
    url = f"/diagrams/{team['diagram_id']}/ai/proposals/{pid}"
    assert client.post(url + "/accept", headers=_h(team["dani"])).status_code == 403
    r = client.post(url + "/reject", headers=_h(team["ana"]))  # la dueña puede
    assert r.status_code == 200 and r.json()["status"] == "rejected" and r.json()["decided_by_name"] == "Ana"
    assert _relations(team) == []


def test_propuesta_desactualizada_no_se_aplica(team, client, monkeypatch):
    pid = _proposal_id(client, team, monkeypatch)
    # Otra persona cambia una clase involucrada antes de que se acepte.
    db = SessionLocal()
    cliente = db.query(Clase).filter(Clase.diagram_id == uuid.UUID(team["diagram_id"]), Clase.nombre == "Cliente").one()
    r = client.post(f"/diagrams/classes/{cliente.id}/attributes", json={"name": "email", "type": "String"},
                    headers=_h(team["dani"]))
    db.close()
    assert r.status_code == 201
    r = client.post(f"/diagrams/{team['diagram_id']}/ai/proposals/{pid}/accept", headers=_h(team["bruno"]))
    assert r.json()["status"] == "stale"
    assert _relations(team) == []


def test_un_cambio_en_otra_clase_no_invalida_la_propuesta(team, client, monkeypatch):
    pid = _proposal_id(client, team, monkeypatch)
    r = client.post(f"/diagrams/{team['diagram_id']}/classes", json={"name": "Producto"}, headers=_h(team["dani"]))
    assert r.status_code == 201
    r = client.post(f"/diagrams/{team['diagram_id']}/ai/proposals/{pid}/accept", headers=_h(team["bruno"]))
    assert r.json()["status"] == "applied"


# ---------------------------------------------------------------------------
# CU-08: configuracion
# ---------------------------------------------------------------------------
def test_asesor_desactivado_no_responde_y_avisa(team, client, monkeypatch):
    seen = _fake_model(monkeypatch, _advisor_script())
    base = f"/diagrams/{team['diagram_id']}/ai/settings"
    assert client.patch(base, json={"enabled": False}, headers=_h(team["bruno"])).status_code == 403  # solo la dueña
    s = client.patch(base, json={"enabled": False}, headers=_h(team["ana"])).json()
    assert s["enabled"] is False and s["mode"] == "on_demand"
    assert client.get(base, headers=_h(team["dani"])).json()["enabled"] is False  # visible para todos
    q = _ask(client, team, "bruno", "@IA ¿cómo relacionamos Cliente y Pedido?")
    assert seen == []  # no se llamo al modelo
    note = _answer_to(team, q["id"])
    assert note.role == ChatRole.ERROR and "desactivado" in note.content and note.addressed_to_name == "Bruno"


def test_sin_propuestas_el_asesor_no_recibe_herramientas(team, client, monkeypatch):
    client.patch(f"/diagrams/{team['diagram_id']}/ai/settings", json={"proposals_enabled": False}, headers=_h(team["ana"]))
    seen = _fake_model(monkeypatch, lambda b, n: {"role": "assistant", "content": "Bruno, conviene 1 a muchos."})
    q = _ask(client, team, "bruno", "@IA ¿cómo relacionamos Cliente y Pedido?")
    assert "tools" not in seen[0]
    assert _answer_to(team, q["id"]).proposal is None


# ---------------------------------------------------------------------------
# Confiabilidad
# ---------------------------------------------------------------------------
def test_una_consulta_en_curso_por_persona(team, client, monkeypatch):
    db = SessionLocal()
    q = ChatMessage(diagram_id=uuid.UUID(team["diagram_id"]), role=ChatRole.USER, author_id=team["bruno"]["id"],
                    author_name="Bruno", content="@IA algo", asks_ai=True, ai_status="running")
    db.add(q)
    db.commit()
    db.close()
    r = client.post(f"/diagrams/{team['diagram_id']}/chat", json={"text": "@IA otra"}, headers=_h(team["bruno"]))
    assert r.status_code == 429
    # Los mensajes normales y las consultas de otros siguen funcionando.
    assert client.post(f"/diagrams/{team['diagram_id']}/chat", json={"text": "hola"}, headers=_h(team["bruno"])).status_code == 201
    _fake_model(monkeypatch, lambda b, n: {"role": "assistant", "content": "Dani, claro."})
    assert client.post(f"/diagrams/{team['diagram_id']}/chat", json={"text": "@IA ¿qué es UML?"},
                       headers=_h(team["dani"])).status_code == 201


def test_consultas_interrumpidas_por_reinicio_se_cierran(team):
    db = SessionLocal()
    q = ChatMessage(diagram_id=uuid.UUID(team["diagram_id"]), role=ChatRole.USER, author_id=team["bruno"]["id"],
                    author_name="Bruno", content="@IA algo", asks_ai=True, ai_status="running")
    dev = ChatMessage(diagram_id=uuid.UUID(team["diagram_id"]), role=ChatRole.USER, author_id=team["dani"]["id"],
                      author_name="Dani", content="@IA en el celu", asks_ai=True, ai_status="device")
    db.add_all([q, dev])
    db.commit()
    qid, devid = q.id, dev.id
    db.close()
    assert chat_service.recover_interrupted_questions() >= 1
    db = SessionLocal()
    try:
        assert db.get(ChatMessage, qid).ai_status == "failed"
        assert db.get(ChatMessage, devid).ai_status == "device"  # la del celular no depende del servidor
        note = db.query(ChatMessage).filter(ChatMessage.reply_to_id == qid).one()
        assert note.role == ChatRole.ERROR and "reinició" in note.content
    finally:
        db.close()


def test_caida_del_proveedor_no_rompe_el_chat(team, client, monkeypatch):
    def handler(request):
        raise httpx.ConnectError("sin conexion")

    real = httpx.Client
    monkeypatch.setattr(llm_providers.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    q = _ask(client, team, "bruno", "@IA ¿cómo relacionamos Cliente y Pedido?")
    err = _answer_to(team, q["id"])
    assert err.role == ChatRole.ERROR and err.addressed_to_name == "Bruno"
    hist = client.get(f"/diagrams/{team['diagram_id']}/chat", headers=_h(team["ana"])).json()["items"]
    assert next(m for m in hist if m["id"] == q["id"])["ai_status"] == "failed"
    # El chat y el diagrama siguen operativos.
    assert client.post(f"/diagrams/{team['diagram_id']}/chat", json={"text": "seguimos"}, headers=_h(team["ana"])).status_code == 201
    assert client.post(f"/diagrams/{team['diagram_id']}/classes", json={"name": "Factura"}, headers=_h(team["ana"])).status_code == 201


# ---------------------------------------------------------------------------
# CU-04: contexto correcto y aislado
# ---------------------------------------------------------------------------
def test_contexto_incluye_multiplicidades_y_no_mezcla_diagramas(team, client, monkeypatch):
    db = SessionLocal()
    did = uuid.UUID(team["diagram_id"])
    cli = db.query(Clase).filter(Clase.diagram_id == did, Clase.nombre == "Cliente").one()
    ped = db.query(Clase).filter(Clase.diagram_id == did, Clase.nombre == "Pedido").one()
    db.add(Relacion(diagram_id=did, origen_id=cli.id, destino_id=ped.id, tipo=RelType.ASSOCIATION,
                    mult_origen_min=1, mult_origen_max=1, mult_destino_min=0, mult_destino_max=None))
    otro = Diagram(title="Otro proyecto", owner_id=team["ana"]["id"])
    db.add(otro)
    db.commit()
    db.add(Clase(nombre="ClaseSecretaDeOtroProyecto", diagram_id=otro.id))
    db.commit()
    otro_id = otro.id
    db.close()
    try:
        seen = _fake_model(monkeypatch, lambda b, n: {"role": "assistant", "content": "Bruno, está bien."})
        _ask(client, team, "bruno", "@IA ¿está bien la cardinalidad entre Cliente y Pedido?")
        prompt = seen[0]["messages"][-1]["content"]
        assert '"mult_origen": "1"' in prompt and '"mult_destino": "*"' in prompt
        assert "Usuario que te consulta: Bruno" in prompt
        assert "ClaseSecretaDeOtroProyecto" not in prompt
    finally:
        db = SessionLocal()
        db.delete(db.get(Diagram, otro_id))
        db.commit()
        db.close()


# ---------------------------------------------------------------------------
# Honestidad del asesor y validacion de propuestas (encontrado con Gemini real)
# ---------------------------------------------------------------------------
def test_si_dice_que_propuso_sin_hacerlo_se_le_insiste(team, client, monkeypatch):
    def script(body, n):
        if n == 1:
            return {"role": "assistant", "content": "Bruno, conviene 1 a muchos. Lo dejé registrado como propuesta."}
        if n == 2:
            assert body["tool_choice"] == "required"
            return _propose(REL_OPS)
        return {"role": "assistant", "content": "Bruno, ahora sí quedó propuesta: Cliente 1 — 0..* Pedido."}

    _fake_model(monkeypatch, script)
    q = _ask(client, team, "bruno", "@IA ¿cómo relacionamos Cliente y Pedido?")
    answer = _answer_to(team, q["id"])
    assert answer.proposal is not None and "ahora sí" in answer.content


def test_si_insiste_en_mentir_se_aclara_que_no_hay_propuesta(team, client, monkeypatch):
    _fake_model(monkeypatch, lambda b, n: {"role": "assistant",
                                          "content": "Bruno, lo dejé registrado como propuesta en el panel."})
    q = _ask(client, team, "bruno", "@IA ¿cómo relacionamos Cliente y Pedido?")
    answer = _answer_to(team, q["id"])
    assert answer.proposal is None
    assert "no quedó registrada una propuesta" in answer.content


def test_no_se_propone_duplicar_una_relacion_existente():
    from app.services.ai_proposals import validate_operations
    snapshot = {
        "clases": [{"nombre": n, "atributos": [], "metodos": []} for n in ("Pedido", "Producto")],
        "relaciones": [{"origen": "Pedido", "destino": "Producto", "tipo": "ASSOCIATION",
                        "mult_origen": "1", "mult_destino": "1"}],
    }
    dup = [{"tool": "create_relation", "args": {"from_class": "Producto", "to_class": "Pedido", "type": "ASSOCIATION"}}]
    _, errors, _ = validate_operations(snapshot, dup)
    assert errors and "delete_relation" in errors[0]
    cambio = [{"tool": "delete_relation", "args": {"from_class": "Pedido", "to_class": "Producto"}},
              {"tool": "create_relation", "args": {"from_class": "Pedido", "to_class": "Producto", "type": "ASSOCIATION",
                                                   "src_multiplicity": "*", "dst_multiplicity": "*"}}]
    ops, errors, touched = validate_operations(snapshot, cambio)
    assert not errors and touched == {"pedido", "producto"} and len(ops) == 2


def test_respuesta_anclada_a_las_clases_reales(team, client, monkeypatch):
    """Visto con Gemini real: "dejé registrada esa propuesta" sin nombrar
    ninguna clase. Se agrega el detalle de los cambios con sus nombres."""
    def script(body, n):
        if n == 1:
            return _propose(REL_OPS)
        return {"role": "assistant", "content": "Bruno, dejé registrada esa propuesta para el equipo."}

    _fake_model(monkeypatch, script)
    q = _ask(client, team, "bruno", "@IA ¿cómo relacionamos Cliente y Pedido?")
    content = _answer_to(team, q["id"]).content
    assert "Cliente" in content and "Pedido" in content
