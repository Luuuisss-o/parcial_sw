"""
Pruebas de la Fase 2 - Prioridad Alta:
  * Chat grupal sincronizado (CU-14)
  * IA orientada al contexto del usuario (CU-16)
  * Visibilidad publica de las consultas a la IA (CU-15)

A diferencia de las suites test_api_qa*.py (caja negra contra el backend en
Docker), esta corre la app EN PROCESO con TestClient contra la base
configurada en backend/.env (DB_URL), con las migraciones aplicadas
(`alembic upgrade head`). Gemini se reemplaza por un doble de prueba: lo que
se verifica es que al modelo le llegue QUIEN pregunta y su historial, y que
pregunta y respuesta se difundan a todos los colaboradores conectados.

    cd backend && pytest tests/test_fase2_chat_ia.py -v
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from passlib.hash import bcrypt

from app.core.security import create_access_token
from app.db import SessionLocal
from app.main import app
from app.models.uml import CollaboratorRole, Diagram, DiagramCollaborator
from app.models.user import User
from app.services import ai_assistant, chat_service
from app.services.ai_assistant import AiCommandResult, Requester, build_prompt


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_user(db, name: str) -> User:
    u = User(
        email=f"fase2.{uuid.uuid4().hex[:8]}@test.local",
        name=name,
        password_hash=bcrypt.hash("x"),
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture()
def team():
    """Un diagrama con dueño (Ana), un colaborador (Bruno) y un extraño (Carla)."""
    db = SessionLocal()
    ana = _make_user(db, "Ana Pérez")
    bruno = _make_user(db, "Bruno Díaz")
    carla = _make_user(db, "Carla Ruiz")
    d = Diagram(title="Fase 2 - chat", owner_id=ana.id)
    db.add(d)
    db.commit()
    db.add(DiagramCollaborator(diagram_id=d.id, user_id=bruno.id, role=CollaboratorRole.EDITOR))
    db.commit()
    data = {
        "diagram_id": str(d.id),
        "ana": {"id": ana.id, "name": ana.name, "token": create_access_token(ana.email)},
        "bruno": {"id": bruno.id, "name": bruno.name, "token": create_access_token(bruno.email)},
        "carla": {"id": carla.id, "name": carla.name, "token": create_access_token(carla.email)},
    }
    yield data
    db.delete(db.get(Diagram, d.id))
    db.commit()
    for u in (ana, bruno, carla):
        db.delete(db.get(User, u.id))
    db.commit()
    db.close()


@pytest.fixture()
def client():
    # Como context manager para que corra el startup (captura del loop que
    # usan las notificaciones realtime disparadas desde las BackgroundTasks).
    with TestClient(app) as c:
        yield c


def _h(user):
    return {"Authorization": f"Bearer {user['token']}"}


def _ws(client, diagram_id, user):
    return client.websocket_connect(f"/diagrams/{diagram_id}/ws?token={user['token']}")


def _wait(ws, event, pred=lambda d: True, max_msgs=50):
    """Lee del socket hasta encontrar `event` que cumpla `pred`."""
    for _ in range(max_msgs):
        msg = ws.receive_json()
        if msg.get("event") == event and pred(msg.get("data")):
            return msg["data"]
    raise AssertionError(f"no llego el evento {event}")


@pytest.fixture()
def fake_ai(monkeypatch):
    """Reemplaza la llamada a Gemini y registra con que contexto se la invoco."""
    calls = []
    behaviour = {"reply": "Listo, cree la clase Factura.", "error": None}

    def _run_command(db, diagram, user_text, requester=None, history=None):
        calls.append({"text": user_text, "requester": requester, "history": list(history or [])})
        if behaviour["error"]:
            raise behaviour["error"]
        return AiCommandResult(reply=behaviour["reply"], actions=[])

    monkeypatch.setattr(ai_assistant, "run_command", _run_command)
    return calls, behaviour


# ---------------------------------------------------------------------------
# Unidades: deteccion de la mencion y armado del contexto
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("@IA qué es una agregación?", (True, "qué es una agregación?")),
    ("@ia, creá la clase Pago", (True, "creá la clase Pago")),
    ("Che @asistente: agregale total a Factura", (True, "Che agregale total a Factura")),
    ("@AI explain inheritance", (True, "explain inheritance")),
    ("hola equipo, ya terminé Cliente", (False, "hola equipo, ya terminé Cliente")),
    ("mandame un mail a ana@ia.com", (False, "mandame un mail a ana@ia.com")),
    ("@iaxyz no es mención", (False, "@iaxyz no es mención")),
    ("@IA", (False, "@IA")),  # mencion sin pregunta: es un mensaje comun
])
def test_parse_ai_mention(text, expected):
    assert chat_service.parse_ai_mention(text) == expected


def test_parse_ai_mention_con_flag_explicito():
    assert chat_service.parse_ai_mention("qué es un DTO?", ask_ai_flag=True) == (True, "qué es un DTO?")


def test_address_reply_garantiza_el_nombre():
    assert chat_service.address_reply("Creé la clase Pago.", "Bruno Díaz") == "Bruno, Creé la clase Pago."
    # Si el modelo ya nombro a la persona no se duplica.
    assert chat_service.address_reply("Bruno, creé la clase Pago.", "Bruno Díaz") == "Bruno, creé la clase Pago."


def test_build_prompt_identifica_al_usuario_y_su_historial():
    p = build_prompt(
        '{"clases": []}', "agregale otro atributo",
        requester=Requester(user_id=1, name="Ana Pérez", email="ana@x.com"),
        history=[("creá la clase Cliente", "Ana, creé Cliente.")],
    )
    assert "Usuario que te consulta: Ana Pérez (ana@x.com)" in p
    assert "Ana Pérez pregunto: creá la clase Cliente" in p
    assert "Vos respondiste: Ana, creé Cliente." in p
    assert p.rstrip().endswith("Instruccion actual de Ana Pérez:\nagregale otro atributo")


# ---------------------------------------------------------------------------
# CU-14: chat grupal sincronizado
# ---------------------------------------------------------------------------

def test_chat_se_difunde_a_todos_los_conectados(client, team):
    did = team["diagram_id"]
    with _ws(client, did, team["ana"]) as ws_ana, _ws(client, did, team["bruno"]) as ws_bruno:
        # Presencia: Ana ve que Bruno se conecto.
        conectados = _wait(ws_ana, "presence", lambda d: len(d) == 2)
        assert {u["name"] for u in conectados} == {"Ana Pérez", "Bruno Díaz"}

        r = client.post(f"/diagrams/{did}/chat", json={"text": "Hola equipo 👋"}, headers=_h(team["ana"]))
        assert r.status_code == 201, r.text
        sent = r.json()
        assert sent["author_name"] == "Ana Pérez"
        assert sent["asks_ai"] is False

        for ws in (ws_ana, ws_bruno):
            m = _wait(ws, "chat.message")
            assert m["id"] == sent["id"]
            assert m["content"] == "Hola equipo 👋"
            assert m["author_name"] == "Ana Pérez"
            assert m["created_at"]  # marca de tiempo

    # El historial persiste para quien entra despues.
    r = client.get(f"/diagrams/{did}/chat", headers=_h(team["bruno"]))
    assert r.status_code == 200
    assert [m["content"] for m in r.json()["items"]] == ["Hola equipo 👋"]


def test_chat_historial_paginado_en_orden(client, team):
    did = team["diagram_id"]
    for i in range(5):
        client.post(f"/diagrams/{did}/chat", json={"text": f"m{i}"}, headers=_h(team["ana"]))
    r = client.get(f"/diagrams/{did}/chat?limit=3", headers=_h(team["ana"])).json()
    assert [m["content"] for m in r["items"]] == ["m2", "m3", "m4"]
    assert r["has_more"] is True
    older = client.get(
        f"/diagrams/{did}/chat?limit=3&before_seq={r['items'][0]['seq']}", headers=_h(team["ana"])
    ).json()
    assert [m["content"] for m in older["items"]] == ["m0", "m1"]
    assert older["has_more"] is False


def test_chat_rechaza_a_quien_no_es_del_diagrama(client, team):
    did = team["diagram_id"]
    assert client.post(f"/diagrams/{did}/chat", json={"text": "hola"}, headers=_h(team["carla"])).status_code == 404
    assert client.get(f"/diagrams/{did}/chat", headers=_h(team["carla"])).status_code == 404
    assert client.post(f"/diagrams/{did}/chat", json={"text": "   "}, headers=_h(team["ana"])).status_code == 422


# ---------------------------------------------------------------------------
# CU-15 / CU-16: consultas a la IA publicas y dirigidas a quien pregunta
# ---------------------------------------------------------------------------

def test_consulta_a_la_ia_es_publica_y_dirigida_al_autor(client, team, fake_ai):
    calls, _ = fake_ai
    did = team["diagram_id"]
    with _ws(client, did, team["ana"]) as ws_ana, _ws(client, did, team["bruno"]) as ws_bruno:
        r = client.post(
            f"/diagrams/{did}/chat", json={"text": "@IA creá la clase Factura"}, headers=_h(team["bruno"])
        )
        assert r.status_code == 201
        pregunta = r.json()
        assert pregunta["asks_ai"] is True

        # Al modelo le llega quien pregunta y el texto sin la mencion.
        assert len(calls) == 1
        assert calls[0]["text"] == "creá la clase Factura"
        assert calls[0]["requester"].name == "Bruno Díaz"
        assert calls[0]["requester"].user_id == team["bruno"]["id"]

        # Ana (que NO pregunto) ve la pregunta de Bruno, el aviso de que la IA
        # esta respondiendo, y la respuesta dirigida a Bruno.
        for ws in (ws_ana, ws_bruno):
            q = _wait(ws, "chat.message", lambda d: d["id"] == pregunta["id"])
            assert q["author_name"] == "Bruno Díaz"
            started = _wait(ws, "ai.started")
            assert started["request_id"] == pregunta["id"]
            assert started["requested_by"]["name"] == "Bruno Díaz"
            a = _wait(ws, "chat.message", lambda d: d["role"] == "ASSISTANT")
            assert a["reply_to_id"] == pregunta["id"]
            assert a["addressed_to_id"] == team["bruno"]["id"]
            assert a["addressed_to_name"] == "Bruno Díaz"
            assert a["content"].startswith("Bruno,")

    hist = client.get(f"/diagrams/{did}/chat", headers=_h(team["ana"])).json()["items"]
    assert [m["role"] for m in hist] == ["USER", "ASSISTANT"]


def test_historial_por_usuario_no_se_mezcla(client, team, fake_ai):
    calls, behaviour = fake_ai
    did = team["diagram_id"]
    behaviour["reply"] = "Ana, creé Cliente."
    client.post(f"/diagrams/{did}/chat", json={"text": "@IA creá Cliente"}, headers=_h(team["ana"]))
    behaviour["reply"] = "Bruno, creé Pedido."
    client.post(f"/diagrams/{did}/chat", json={"text": "@IA creá Pedido"}, headers=_h(team["bruno"]))
    client.post(f"/diagrams/{did}/chat", json={"text": "mensaje normal, sin IA"}, headers=_h(team["ana"]))
    behaviour["reply"] = "Ana, listo."
    client.post(f"/diagrams/{did}/chat", json={"text": "@IA agregale email"}, headers=_h(team["ana"]))

    assert len(calls) == 3  # el mensaje normal no invoca a la IA
    tercera = calls[2]
    assert tercera["requester"].name == "Ana Pérez"
    # Solo el hilo de Ana, nunca la consulta de Bruno.
    assert tercera["history"] == [("creá Cliente", "Ana, creé Cliente.")]


def test_error_de_la_ia_queda_publico_y_dirigido(client, team, fake_ai):
    _, behaviour = fake_ai
    behaviour["error"] = RuntimeError("GEMINI_API_KEY no esta configurada en el backend (.env).")
    did = team["diagram_id"]
    with _ws(client, did, team["ana"]) as ws_ana:
        client.post(f"/diagrams/{did}/chat", json={"text": "qué es UML?", "ask_ai": True}, headers=_h(team["bruno"]))
        err = _wait(ws_ana, "chat.message", lambda d: d["role"] == "ERROR")
        assert err["addressed_to_name"] == "Bruno Díaz"
        assert "GEMINI_API_KEY" in err["content"]
        ev = _wait(ws_ana, "ai.error")
        assert ev["requested_by"]["name"] == "Bruno Díaz"


def test_endpoint_ai_command_tambien_es_publico(client, team, fake_ai):
    calls, _ = fake_ai
    did = team["diagram_id"]
    r = client.post(f"/diagrams/{did}/ai/command", json={"text": "creá la clase Pago"}, headers=_h(team["ana"]))
    assert r.status_code == 202
    assert r.json()["status"] == "processing"
    assert calls[0]["requester"].name == "Ana Pérez"
    hist = client.get(f"/diagrams/{did}/chat", headers=_h(team["bruno"])).json()["items"]
    assert hist[0]["content"] == "creá la clase Pago" and hist[0]["asks_ai"] is True
    assert hist[1]["role"] == "ASSISTANT" and hist[1]["reply_to_id"] == r.json()["request_id"]
