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
from app.services.ai_assistant import (
    MODE_AUTO, MODE_MENTOR, AiCommandResult, Requester, TeamMessage, build_prompt, classify_intent,
)


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

    def _run_command(db, diagram, user_text, requester=None, history=None, team_context=None, mode=None,
                     solutions_enabled=False):
        calls.append({
            "text": user_text, "requester": requester, "history": list(history or []),
            "team": list(team_context or []), "solutions_enabled": solutions_enabled,
        })
        if behaviour["error"]:
            raise behaviour["error"]
        return AiCommandResult(reply=behaviour["reply"], actions=[], mode=behaviour.get("mode", "AUTO"))

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
    assert p.rstrip().endswith("Consulta actual de Ana Pérez (respondele a esta):\nagregale otro atributo")


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


# ---------------------------------------------------------------------------
# Prioridad media: rol de mentoria (CU-15) y memoria de contexto hibrida
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,mode", [
    ("¿Qué es un requerimiento delegado?", MODE_MENTOR),
    ("qué diferencia hay entre agregación y composición?", MODE_MENTOR),
    ("Explicame el patrón Observer con un ejemplo", MODE_MENTOR),
    ("¿Es correcto que Pedido herede de Cliente?", MODE_MENTOR),
    ("¿Qué hace un DTO?", MODE_MENTOR),
    ("Cuál es la multiplicidad correcta entre Cliente y Pedido?", MODE_MENTOR),
    ("creá la clase Factura", MODE_AUTO),
    ("agregale email a Cliente", MODE_AUTO),
    ("¿Qué es una composición? aplicala entre Pedido y Detalle", MODE_AUTO),
    ("relacioná Cliente y Pedido de uno a muchos", MODE_AUTO),
    ("hola", MODE_AUTO),
    # Casos detectados en la prueba con Gemini real:
    ("¿Pedido debería heredar de Cliente?", MODE_MENTOR),
    ("explicámelo con un ejemplo de lo que propuso Admin", MODE_MENTOR),
    ("¿Cliente puede tener muchos pedidos?", MODE_MENTOR),
    ("¿le agregás email a Cliente?", MODE_AUTO),
    ("¿podés crear la clase Pago?", MODE_AUTO),
    ("ponele total a Pedido", MODE_AUTO),
    ("armame el diagrama de una veterinaria", MODE_AUTO),
    # Ejemplo literal del docente (audio de la Fase 2):
    ("No me acuerdo qué es un atributo derivado", MODE_MENTOR),
    ("tengo una duda con la multiplicidad", MODE_MENTOR),
])
def test_classify_intent(text, mode):
    assert classify_intent(text) == mode


class _FakeGenai:
    """Doble del cliente de Gemini para ejercitar el run_command REAL."""

    def __init__(self, output="Ana, una agregación es..."):
        self.calls = []
        self.output = output

    def client(self, api_key):
        from types import SimpleNamespace
        fake = self

        class _Interactions:
            def create(self, **kw):
                fake.calls.append(kw)
                return SimpleNamespace(steps=[], output_text=fake.output, id="i1")

        return SimpleNamespace(interactions=_Interactions())


@pytest.fixture()
def fake_genai(monkeypatch):
    from app.core.config import settings
    fake = _FakeGenai()
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(ai_assistant.genai, "Client", fake.client)
    return fake


def test_mentoria_no_recibe_herramientas_y_no_modifica(team, fake_genai):
    db = SessionLocal()
    try:
        d = db.get(Diagram, uuid.UUID(team["diagram_id"]))
        r = ai_assistant.run_command(
            db, d, "¿Qué es un requerimiento delegado?", requester=Requester(1, "Ana Pérez", "a@x.com"),
        )
    finally:
        db.close()
    assert r.mode == MODE_MENTOR and r.actions == []
    call = fake_genai.calls[0]
    assert "tools" not in call  # imposible editar el diagrama en modo mentor
    assert "MENTOR DE DISENO DE SOFTWARE" in call["system_instruction"]
    assert "sin modificar el diagrama" in call["input"]


def test_modo_auto_si_recibe_herramientas(team, fake_genai):
    db = SessionLocal()
    try:
        d = db.get(Diagram, uuid.UUID(team["diagram_id"]))
        r = ai_assistant.run_command(db, d, "creá la clase Pago", requester=Requester(1, "Ana Pérez"))
    finally:
        db.close()
    assert r.mode == MODE_AUTO
    assert "tools" in fake_genai.calls[0]


def test_build_prompt_memoria_hibrida_en_niveles():
    p = build_prompt(
        '{"clases": []}', "y cómo lo aplico acá?",
        requester=Requester(user_id=1, name="Ana Pérez"),
        history=[("qué es una composición?", "Ana, una composición es...")],
        team_context=[
            TeamMessage(author="Bruno Díaz", content="propongo que Pedido tenga DetallePedido"),
            TeamMessage(author="Asistente IA", content="Bruno, creé DetallePedido.", is_ai=True,
                        addressed_to="Bruno Díaz"),
        ],
    )
    i_diag = p.index("[Contexto global] Estado actual del diagrama")
    i_team = p.index("[Contexto global] Conversacion reciente del equipo")
    i_hilo = p.index("[Hilo individual] Consultas previas de Ana Pérez")
    i_now = p.index("Consulta actual de Ana Pérez")
    assert i_diag < i_team < i_hilo < i_now
    assert "- Bruno Díaz: propongo que Pedido tenga DetallePedido" in p
    assert "- Vos (IA) respondiste a Bruno Díaz: Bruno, creé DetallePedido." in p


def test_memoria_hibrida_en_el_flujo_del_chat(client, team, fake_ai):
    calls, behaviour = fake_ai
    did = team["diagram_id"]
    ana, bruno = team["ana"], team["bruno"]
    behaviour["reply"] = "Ana, una composición es..."
    client.post(f"/diagrams/{did}/chat", json={"text": "@IA qué es una composición?"}, headers=_h(ana))
    client.post(f"/diagrams/{did}/chat", json={"text": "propongo que Pedido tenga DetallePedido"},
                headers=_h(bruno))
    behaviour["reply"] = "Bruno, creé DetallePedido."
    client.post(f"/diagrams/{did}/chat", json={"text": "@IA creá la clase DetallePedido"}, headers=_h(bruno))
    behaviour["reply"] = "Ana, en su diagrama..."
    client.post(f"/diagrams/{did}/chat", json={"text": "@IA y cómo la aplico con lo que propuso Bruno?"},
                headers=_h(ana))

    last = calls[-1]
    # Hilo individual: solo lo de Ana.
    assert last["history"] == [("qué es una composición?", "Ana, una composición es...")]
    # Contexto global: lo que dijo/pidió Bruno y lo que la IA le respondió...
    team_lines = [(m.author, m.content, m.is_ai) for m in last["team"]]
    assert ("Bruno Díaz", "propongo que Pedido tenga DetallePedido", False) in team_lines
    assert ("Bruno Díaz", "(le pregunto a la IA) creá la clase DetallePedido", False) in team_lines
    assert ("Asistente IA", "Bruno, creé DetallePedido.", True) in team_lines
    # ...pero NO el propio ida y vuelta de Ana con la IA (ya va en su hilo).
    assert not any("composición" in c for _, c, _ in team_lines)


def test_respuesta_de_mentoria_queda_marcada(client, team, fake_ai):
    _, behaviour = fake_ai
    behaviour.update(reply="Bruno, un requerimiento delegado es...", mode=MODE_MENTOR)
    did = team["diagram_id"]
    client.post(f"/diagrams/{did}/chat", json={"text": "@IA qué es un requerimiento delegado?"},
                headers=_h(team["bruno"]))
    hist = client.get(f"/diagrams/{did}/chat", headers=_h(team["ana"])).json()["items"]
    assert hist[-1]["role"] == "ASSISTANT" and hist[-1]["ai_mode"] == MODE_MENTOR
    assert hist[0]["ai_mode"] is None


def test_ia_ubica_clases_nuevas_sin_superponerlas(client, team):
    """Antes todas las clases creadas por la IA quedaban en (0, 0)."""
    from app.services.ai_tools import DiagramToolExecutor
    db = SessionLocal()
    try:
        d = db.get(Diagram, uuid.UUID(team["diagram_id"]))
        ex = DiagramToolExecutor(db, d)
        for n in ("A", "B", "C"):
            ex.create_class(name=n)
        # Coordenadas que se pisan, como las que manda Gemini: se recolocan.
        ex.create_class(name="D", x_grid=1, y_grid=1)
        ex.create_class(name="E", x_grid=3, y_grid=1)
        # Una posicion libre pedida explicitamente se respeta.
        ex.create_class(name="Fija", x_grid=100, y_grid=100)
        clases = {c["nombre"]: c for c in ex.snapshot()["clases"]}
    finally:
        db.close()
    assert (clases["Fija"]["x_grid"], clases["Fija"]["y_grid"]) == (100, 100)
    rects = [(c["x_grid"], c["y_grid"], c["x_grid"] + c["w_grid"], c["y_grid"] + 10)
             for n, c in clases.items() if n != "Fija"]
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            assert not (a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]), (a, b)


# ---------------------------------------------------------------------------
# Audio del docente: "la IA va a tener la capacidad de entregar soluciones
# cuando asi se lo requieran. Eso va a ser configurable".
# ---------------------------------------------------------------------------

def test_configuracion_entrega_de_soluciones(client, team, fake_ai):
    calls, _ = fake_ai
    did = team["diagram_id"]
    ana, bruno = team["ana"], team["bruno"]

    assert client.get(f"/diagrams/{did}/ai/settings", headers=_h(bruno)).json() == {"solutions_enabled": False}
    # Un colaborador no puede cambiarla; un extraño ni siquiera verla.
    assert client.patch(f"/diagrams/{did}/ai/settings", json={"solutions_enabled": True},
                        headers=_h(bruno)).status_code == 403
    assert client.get(f"/diagrams/{did}/ai/settings", headers=_h(team["carla"])).status_code == 404

    client.post(f"/diagrams/{did}/chat", json={"text": "@IA armame el diagrama de una veterinaria"}, headers=_h(bruno))
    assert calls[-1]["solutions_enabled"] is False

    with _ws(client, did, bruno) as ws_bruno:
        r = client.patch(f"/diagrams/{did}/ai/settings", json={"solutions_enabled": True}, headers=_h(ana))
        assert r.status_code == 200 and r.json() == {"solutions_enabled": True}
        ev = _wait(ws_bruno, "ai.settings")
        assert ev == {"solutions_enabled": True, "changed_by": "Ana Pérez"}

    client.post(f"/diagrams/{did}/chat", json={"text": "@IA armame el diagrama de una veterinaria"}, headers=_h(bruno))
    assert calls[-1]["solutions_enabled"] is True
    assert client.get(f"/diagrams/{did}", headers=_h(bruno)).json()["ai_solutions_enabled"] is True


def test_prompt_segun_configuracion_y_rol_senior(team, fake_genai):
    db = SessionLocal()
    try:
        d = db.get(Diagram, uuid.UUID(team["diagram_id"]))
        ai_assistant.run_command(db, d, "armame el diagrama de una veterinaria",
                                 requester=Requester(1, "Ana Pérez"), solutions_enabled=False)
        ai_assistant.run_command(db, d, "armame el diagrama de una veterinaria",
                                 requester=Requester(1, "Ana Pérez"), solutions_enabled=True)
    finally:
        db.close()
    off, on = (c["system_instruction"] for c in fake_genai.calls)
    assert "desarrollador senior y moderador" in off
    assert "Entrega de soluciones DESACTIVADA" in off and "soluciones ACTIVADA" not in off
    assert "Entrega de soluciones ACTIVADA" in on and "{solutions_rule}" not in on
