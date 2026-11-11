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
                     solutions_enabled=False, proposals_enabled=False, **kw):
        calls.append({
            "text": user_text, "requester": requester, "history": list(history or []),
            "team": list(team_context or []), "solutions_enabled": solutions_enabled,
            "proposals_enabled": proposals_enabled,
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


def test_borrar_el_diagrama_mientras_la_ia_responde_no_rompe(client, team, monkeypatch):
    """El dueño borra el diagrama mientras la IA piensa: la tarea en segundo
    plano termina sin excepcion (antes intentaba guardar el aviso de error
    sobre una pregunta que ya no existia)."""
    db = SessionLocal()
    d = Diagram(title="se borra mientras responde", owner_id=team["ana"]["id"])
    db.add(d)
    db.commit()
    did = str(d.id)

    def _run_command(db_bg, diagram, *a, **k):
        other = SessionLocal()
        other.delete(other.get(Diagram, diagram.id))
        other.commit()
        other.close()
        raise RuntimeError("la base rechaza escribir en un diagrama borrado")

    monkeypatch.setattr(ai_assistant, "run_command", _run_command)
    r = client.post(f"/diagrams/{did}/chat", json={"text": "creá la clase Pago", "ask_ai": True},
                    headers=_h(team["ana"]))
    assert r.status_code in (200, 201, 202)
    db.expire_all()
    assert db.get(Diagram, uuid.UUID(did)) is None
    db.close()


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
    # Un verbo de edición en infinitivo dentro de una pregunta teórica no es
    # un pedido (antes caía en modo edición y la respuesta se reemplazaba por
    # "No apliqué ningún cambio en el diagrama...").
    ("en que contexto se recomienda crear una base de datos no relacional?", MODE_MENTOR),
    ("¿cuándo conviene agregar un atributo derivado?", MODE_MENTOR),
    ("¿Cómo puedo relacionar dos clases de muchos a muchos?", MODE_MENTOR),
    ("how to create an association class?", MODE_MENTOR),
    ("crear la clase Factura", MODE_AUTO),
    ("¿qué tal si creás la clase Pago?", MODE_AUTO),
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

    assert client.get(f"/diagrams/{did}/ai/settings", headers=_h(bruno)).json()["solutions_enabled"] is False
    # Un colaborador no puede cambiarla; un extraño ni siquiera verla.
    assert client.patch(f"/diagrams/{did}/ai/settings", json={"solutions_enabled": True},
                        headers=_h(bruno)).status_code == 403
    assert client.get(f"/diagrams/{did}/ai/settings", headers=_h(team["carla"])).status_code == 404

    client.post(f"/diagrams/{did}/chat", json={"text": "@IA armame el diagrama de una veterinaria"}, headers=_h(bruno))
    assert calls[-1]["solutions_enabled"] is False

    with _ws(client, did, bruno) as ws_bruno:
        r = client.patch(f"/diagrams/{did}/ai/settings", json={"solutions_enabled": True}, headers=_h(ana))
        assert r.status_code == 200 and r.json()["solutions_enabled"] is True
        ev = _wait(ws_bruno, "ai.settings")
        assert ev["solutions_enabled"] is True and ev["changed_by"] == "Ana Pérez"

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


# ---------------------------------------------------------------------------
# CU-17: proveedor de IA configurable (Gemini o modelo local OpenAI-compatible)
# ---------------------------------------------------------------------------
import json as _json

import httpx

from app.services import llm_providers


def _fake_openai_server(monkeypatch, *, script):
    """Reemplaza el transporte HTTP del proveedor OpenAI-compatible por un
    servidor falso (como Ollama/LM Studio) que responde segun `script`."""
    requests = []

    def handler(request: httpx.Request):
        body = _json.loads(request.content)
        requests.append({"url": str(request.url), "auth": request.headers.get("authorization"), "body": body})
        return httpx.Response(200, json={"choices": [{"message": script(body, len(requests))}]})

    real_client = httpx.Client
    monkeypatch.setattr(
        llm_providers.httpx, "Client",
        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
    )
    return requests


def test_openai_compatible_loop_de_herramientas(team, monkeypatch, client):
    def script(body, n):
        if n == 1:  # el modelo local pide crear la clase
            return {"role": "assistant", "content": None, "tool_calls": [{
                "id": "c1", "type": "function",
                "function": {"name": "create_class", "arguments": _json.dumps({"name": "Factura"})},
            }]}
        tool_msg = body["messages"][-1]
        assert tool_msg["role"] == "tool" and tool_msg["tool_call_id"] == "c1"
        return {"role": "assistant", "content": "Ana, creé la clase Factura."}

    reqs = _fake_openai_server(monkeypatch, script=script)
    cfg = llm_providers.ProviderConfig(llm_providers.PROVIDER_OPENAI, "llama3.2", "http://localhost:11434/v1", "tok")
    db = SessionLocal()
    try:
        d = db.get(Diagram, uuid.UUID(team["diagram_id"]))
        r = ai_assistant.run_command(db, d, "creá la clase Factura", requester=Requester(1, "Ana Pérez"), provider=cfg)
    finally:
        db.close()
    assert r.reply == "Ana, creé la clase Factura."
    assert [a["tool"] for a in r.actions] == ["create_class"]
    assert r.model_label == "llama3.2 (localhost)"
    assert reqs[0]["url"] == "http://localhost:11434/v1/chat/completions"
    assert reqs[0]["auth"] == "Bearer tok"
    assert reqs[0]["body"]["model"] == "llama3.2"
    assert reqs[0]["body"]["messages"][0]["role"] == "system"
    assert reqs[0]["body"]["tools"][0]["type"] == "function"


def test_openai_compatible_mentoria_sin_herramientas(team, monkeypatch, client):
    reqs = _fake_openai_server(monkeypatch, script=lambda b, n: {"role": "assistant", "content": "Ana, es..."})
    cfg = llm_providers.ProviderConfig(llm_providers.PROVIDER_OPENAI, "qwen2.5", "http://colab.example/v1")
    db = SessionLocal()
    try:
        d = db.get(Diagram, uuid.UUID(team["diagram_id"]))
        r = ai_assistant.run_command(db, d, "¿qué es un atributo derivado?", requester=Requester(1, "Ana Pérez"),
                                     provider=cfg)
    finally:
        db.close()
    assert r.mode == MODE_MENTOR
    assert "tools" not in reqs[0]["body"]
    assert reqs[0]["auth"] is None


def test_configurar_proveedor_local_por_diagrama(client, team, monkeypatch, fake_ai):
    did = team["diagram_id"]
    ana, bruno = team["ana"], team["bruno"]
    url = f"/diagrams/{did}/ai/settings"

    s = client.get(url, headers=_h(bruno)).json()
    assert s["provider"] == "gemini" and s["provider_is_default"] is True

    # Faltan endpoint/modelo -> 422; un colaborador no puede -> 403; URL invalida -> 422
    assert client.patch(url, json={"provider": "openai_compatible"}, headers=_h(ana)).status_code == 422
    assert client.patch(url, json={"provider": "openai_compatible", "base_url": "ftp://x", "model": "m"},
                        headers=_h(ana)).status_code == 422
    assert client.patch(url, json={"provider": "gemini"}, headers=_h(bruno)).status_code == 403

    r = client.patch(url, json={"provider": "openai_compatible", "base_url": "http://192.168.0.10:11434/v1/",
                                "model": "llama3.2", "api_key": "secreto"}, headers=_h(ana))
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["provider"] == "openai_compatible" and out["model"] == "llama3.2"
    assert out["base_url"] == "http://192.168.0.10:11434/v1"
    assert out["has_api_key"] is True and "secreto" not in r.text  # el token nunca vuelve

    # Las consultas del chat usan el proveedor del diagrama y la respuesta dice que modelo fue
    calls, _ = fake_ai
    used = []
    real = ai_assistant.run_command
    monkeypatch.setattr(ai_assistant, "run_command", lambda db, diagram, *a, **k: (
        used.append(llm_providers.config_for(diagram)), real(db, diagram, *a, **k))[1])
    client.post(f"/diagrams/{did}/chat", json={"text": "@IA hola"}, headers=_h(bruno))
    assert used[0].kind == "openai_compatible" and used[0].api_key == "secreto"

    # Volver al proveedor por defecto borra endpoint, modelo y token
    out = client.patch(url, json={"provider": "default"}, headers=_h(ana)).json()
    assert out["provider_is_default"] is True and out["has_api_key"] is False and out["base_url"] is None


def test_probar_conexion_reporta_error_claro(client, team):
    did = team["diagram_id"]
    client.patch(f"/diagrams/{did}/ai/settings", json={"provider": "openai_compatible",
                 "base_url": "http://127.0.0.1:9/v1", "model": "llama3.2"}, headers=_h(team["ana"]))
    r = client.post(f"/diagrams/{did}/ai/settings/test", headers=_h(team["ana"])).json()
    assert r["ok"] is False and "No se pudo conectar" in r["detail"]
    assert client.post(f"/diagrams/{did}/ai/settings/test", headers=_h(team["bruno"])).status_code == 403


def test_si_el_modelo_inventa_cambios_se_le_exige_usar_herramientas(team, monkeypatch, client):
    """Visto con Gemini real via la capa OpenAI-compatible: respondio "creé la
    clase Factura" sin llamar a ninguna herramienta (el diagrama no cambio)."""
    def script(body, n):
        if n == 1:
            assert "tool_choice" not in body
            return {"role": "assistant", "content": "Ana, ya creé la clase Factura."}  # mentira
        if n == 2:
            assert body["tool_choice"] == "required"
            assert "No ejecutaste ninguna herramienta" in body["messages"][-1]["content"]
            return {"role": "assistant", "content": None, "tool_calls": [{
                "id": "c1", "type": "function",
                "function": {"name": "create_class", "arguments": '{"name": "Factura"}'}}]}
        return {"role": "assistant", "content": "Ana, creé la clase Factura."}

    _fake_openai_server(monkeypatch, script=script)
    cfg = llm_providers.ProviderConfig(llm_providers.PROVIDER_OPENAI, "llama3.2", "http://localhost:11434/v1")
    db = SessionLocal()
    try:
        d = db.get(Diagram, uuid.UUID(team["diagram_id"]))
        r = ai_assistant.run_command(db, d, "creá la clase Factura", requester=Requester(1, "Ana Pérez"), provider=cfg)
        nombres = [c["nombre"] for c in ai_assistant.DiagramToolExecutor(db, d).snapshot()["clases"]]
    finally:
        db.close()
    assert [a["tool"] for a in r.actions] == ["create_class"]
    assert "Factura" in nombres


# ---------------------------------------------------------------------------
# Modelo personalizado que corre en el CELULAR: alojamiento y respuestas
# generadas en el dispositivo
# ---------------------------------------------------------------------------
import hashlib

from app.models.user import Role


@pytest.fixture()
def models_dir(tmp_path, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "MODELS_DIR", str(tmp_path / "models"))
    return tmp_path / "models"


@pytest.fixture()
def admin(team):
    db = SessionLocal()
    u = db.get(User, team["ana"]["id"])
    u.role = Role.admin
    db.commit()
    db.close()
    return team["ana"]


def test_alojar_y_descargar_modelo_personalizado(client, team, admin, models_dir):
    fake_gguf = b"GGUF" + bytes(range(256)) * 400
    h = _h(admin)
    assert client.get("/models/assistant", headers=h).json() == {
        "available": False, "version": None, "sha256": None, "size_bytes": None, "base_model": None,
        "notes": None, "uploaded_at": None, "uploaded_by": None, "download_path": None}

    # Un colaborador comun no puede publicar; un archivo que no es GGUF se rechaza
    files = {"file": ("m.gguf", fake_gguf, "application/octet-stream")}
    assert client.put("/models/assistant", files=files, data={"version": "1"}, headers=_h(team["bruno"])).status_code == 403
    bad = {"file": ("m.gguf", b"PK\x03\x04zip", "application/octet-stream")}
    assert client.put("/models/assistant", files=bad, data={"version": "1"}, headers=h).status_code == 422
    assert client.put("/models/assistant", files=files, data={"version": "a b"}, headers=h).status_code == 422

    r = client.put("/models/assistant", files=files,
                   data={"version": "2026.11.08-1", "base_model": "google/gemma-3-1b-it"}, headers=h)
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["available"] and m["sha256"] == hashlib.sha256(fake_gguf).hexdigest()
    assert m["size_bytes"] == len(fake_gguf) and m["download_path"] == "/models/assistant/download"

    # Cualquier usuario logueado lo descarga; soporta reanudar con Range
    full = client.get("/models/assistant/download", headers=_h(team["bruno"]))
    assert full.status_code == 200 and full.content == fake_gguf
    part = client.get("/models/assistant/download", headers={**_h(team["bruno"]), "Range": "bytes=100-"})
    assert part.status_code == 206 and part.content == fake_gguf[100:]
    assert client.get("/models/assistant/download").status_code in (401, 403)


def test_consulta_respondida_por_el_modelo_del_celular(client, team, fake_ai):
    calls, behaviour = fake_ai
    did = team["diagram_id"]
    ana, bruno = team["ana"], team["bruno"]
    # Historial previo de Bruno con la IA (del servidor) + un mensaje de Ana al equipo
    behaviour["reply"] = "Bruno, una clase abstracta es..."
    client.post(f"/diagrams/{did}/chat", json={"text": "@IA qué es una clase abstracta?"}, headers=_h(bruno))
    client.post(f"/diagrams/{did}/chat", json={"text": "usemos herencia para Persona"}, headers=_h(ana))
    n_calls = len(calls)

    with _ws(client, did, ana) as ws_ana:
        q = client.post(f"/diagrams/{did}/chat",
                        json={"text": "@IA no me acuerdo qué es un atributo derivado", "answer_on_device": True},
                        headers=_h(bruno)).json()
        assert len(calls) == n_calls  # el servidor NO llamo a ningun modelo
        started = _wait(ws_ana, "ai.started", lambda d: d["request_id"] == q["id"])
        assert started["on_device"] is True and started["requested_by"]["name"] == "Bruno Díaz"

        # El celular pide el contexto (misma memoria hibrida que el servidor)
        assert client.get(f"/diagrams/{did}/chat/{q['id']}/context", headers=_h(ana)).status_code == 403
        ctx = client.get(f"/diagrams/{did}/chat/{q['id']}/context", headers=_h(bruno)).json()
        assert ctx["question"] == "no me acuerdo qué es un atributo derivado"
        assert ctx["requester_name"] == "Bruno Díaz" and ctx["mode"] == "MENTOR"
        assert ctx["history"] == [{"question": "qué es una clase abstracta?", "answer": "Bruno, una clase abstracta es..."}]
        assert {"author": "Ana Pérez", "content": "usemos herencia para Persona", "is_ai": False,
                "addressed_to": None} in ctx["team_context"]
        assert "clases" in ctx["diagram"] and ctx["solutions_enabled"] is False

        # Solo el autor publica la respuesta de su modelo local
        body = {"content": "un atributo derivado se calcula a partir de otros.", "ai_mode": "MENTOR",
                "model_label": "Gemma 3 1B UML (móvil)"}
        assert client.post(f"/diagrams/{did}/chat/{q['id']}/answer", json=body, headers=_h(ana)).status_code == 403
        r = client.post(f"/diagrams/{did}/chat/{q['id']}/answer", json=body, headers=_h(bruno))
        assert r.status_code == 201, r.text
        a = _wait(ws_ana, "chat.message", lambda d: d["role"] == "ASSISTANT" and d["reply_to_id"] == q["id"])
        assert a["content"].startswith("Bruno,")  # dirigida por nombre aunque el modelo chico lo olvide
        assert a["addressed_to_name"] == "Bruno Díaz" and a["ai_model_label"] == "Gemma 3 1B UML (móvil)"
        assert a["ai_mode"] == "MENTOR"
        _wait(ws_ana, "ai.done", lambda d: d["request_id"] == q["id"])

    assert client.post(f"/diagrams/{did}/chat/{q['id']}/answer", json=body, headers=_h(bruno)).status_code == 409


def test_error_del_modelo_del_celular_queda_publico(client, team):
    did = team["diagram_id"]
    q = client.post(f"/diagrams/{did}/chat", json={"text": "@IA creá Pago", "answer_on_device": True},
                    headers=_h(team["bruno"])).json()
    r = client.post(f"/diagrams/{did}/chat/{q['id']}/answer",
                    json={"error": "El modelo local no está descargado.", "model_label": "Gemma (móvil)"},
                    headers=_h(team["bruno"]))
    assert r.status_code == 201 and r.json()["role"] == "ERROR"
    assert r.json()["content"] == "Bruno, El modelo local no está descargado."


def test_clases_creadas_sin_coordenadas_no_se_superponen(client, team):
    """La app movil crea clases sin posicion: antes quedaban todas en (0, 0)."""
    did = team["diagram_id"]
    h = _h(team["ana"])
    pos = [client.post(f"/diagrams/{did}/classes", json={"name": n}, headers=h).json() for n in ("A", "B", "C")]
    coords = {(c["x_grid"], c["y_grid"]) for c in pos}
    assert len(coords) == 3
    # Con coordenadas explicitas (la web) se respetan tal cual, aunque sean (0, 0).
    c = client.post(f"/diagrams/{did}/classes", json={"name": "D", "x_grid": 0, "y_grid": 0}, headers=h).json()
    assert (c["x_grid"], c["y_grid"]) == (0, 0)
