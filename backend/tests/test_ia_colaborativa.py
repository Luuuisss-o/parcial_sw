"""
La IA del equipo como un desarrollador más, trabajando a la vez con varios
integrantes del mismo diagrama:

  * atiende las consultas de varios desarrolladores EN PARALELO (cada una en
    su hilo, sin esperar a la de otro), y cada respuesta va dirigida a quien
    preguntó y la ve todo el equipo;
  * sus ediciones simultáneas sobre un mismo diagrama no se pisan (dos
    pedidos de "creá Cliente" al mismo tiempo dejan una sola clase);
  * respeta la exclusión mutua de los humanos: no toca una clase que otro
    integrante tiene tomada en el editor.

Corre en proceso contra la base configurada (como test_fase2_chat_ia.py).
El modelo se reemplaza por un doble lento: lo que se prueba es la
concurrencia del backend, no la calidad de la respuesta.
"""
import threading
import time
import uuid

import pytest
from passlib.hash import bcrypt

from app.db import SessionLocal
from app.models.chat import ChatMessage, ChatRole
from app.models.uml import Clase, Diagram, DiagramCollaborator, CollaboratorRole
from app.models.user import User
from app.services import ai_assistant, chat_service
from app.services.ai_assistant import AiCommandResult
from app.services.ai_tools import DiagramToolExecutor, ToolError
from app.services.locks import LockInfo, lock_manager


def _user(db, name):
    u = User(email=f"colab.{uuid.uuid4().hex[:8]}@test.local", name=name, password_hash=bcrypt.hash("x"))
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture()
def equipo():
    db = SessionLocal()
    ana, beto, caro = _user(db, "Ana"), _user(db, "Beto"), _user(db, "Caro")
    d = Diagram(title="IA colaborativa", owner_id=ana.id)
    db.add(d)
    db.commit()
    for u in (beto, caro):
        db.add(DiagramCollaborator(diagram_id=d.id, user_id=u.id, role=CollaboratorRole.EDITOR))
    db.commit()
    yield {"db": db, "diagram": d, "users": [ana, beto, caro]}
    db.rollback()
    db.delete(db.get(Diagram, d.id))
    for u in (ana, beto, caro):
        db.delete(db.get(User, u.id))
    db.commit()
    db.close()


def test_atiende_a_varios_desarrolladores_en_paralelo(equipo, monkeypatch):
    """Tres integrantes preguntan a la vez: las tres consultas se procesan
    en paralelo (no en fila) y cada respuesta va a quien preguntó."""
    db, d, users = equipo["db"], equipo["diagram"], equipo["users"]
    DEMORA = 1.0
    en_curso, max_en_curso, guard = [0], [0], threading.Lock()

    def _lento(db_bg, diagram, user_text, requester=None, **kw):
        with guard:
            en_curso[0] += 1
            max_en_curso[0] = max(max_en_curso[0], en_curso[0])
        time.sleep(DEMORA)
        with guard:
            en_curso[0] -= 1
        return AiCommandResult(reply=f"Respuesta para {requester.name}: {user_text}")

    monkeypatch.setattr(ai_assistant, "run_command", _lento)

    preguntas = [chat_service.create_user_message(db, d, u, f"pregunta de {u.name}", asks_ai=True) for u in users]
    hilos = [threading.Thread(target=chat_service.run_ai_question_background, args=(q.id,)) for q in preguntas]
    t0 = time.monotonic()
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    total = time.monotonic() - t0

    assert max_en_curso[0] == 3, "las tres consultas tienen que correr al mismo tiempo"
    assert total < DEMORA * 2, f"en fila habrían tardado {DEMORA * 3:.0f}s; tardaron {total:.1f}s"

    db.expire_all()
    for q, u in zip(preguntas, users):
        resp = (db.query(ChatMessage)
                .filter(ChatMessage.reply_to_id == q.id, ChatMessage.role == ChatRole.ASSISTANT).one())
        assert u.name in resp.content and f"pregunta de {u.name}" in resp.content
        assert db.get(ChatMessage, q.id).ai_status == chat_service.AI_COMPLETED


def test_ediciones_simultaneas_no_se_pisan(equipo):
    """Seis consultas piden crear la misma clase en el mismo instante: queda
    UNA sola, y las demás reciben el error de nombre repetido."""
    d = equipo["diagram"]
    did = d.id  # leído acá: la sesión del fixture no se comparte entre hilos
    N = 6
    barrera = threading.Barrier(N, timeout=30)
    resultados = []

    def crear(i):
        s = SessionLocal()
        try:
            ex = DiagramToolExecutor(s, s.get(Diagram, did), actor_email=f"dev{i}@test.local")
            barrera.wait()
            try:
                ex.create_class("Cliente")
                resultados.append("ok")
            except ToolError:
                resultados.append("repetida")
        except Exception as e:  # que un hilo caído se vea en la aserción
            resultados.append(f"error: {type(e).__name__}: {e}")
        finally:
            s.close()

    hilos = [threading.Thread(target=crear, args=(i,)) for i in range(N)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert resultados.count("ok") == 1 and resultados.count("repetida") == N - 1
    db = equipo["db"]
    db.expire_all()
    assert db.query(Clase).filter(Clase.diagram_id == d.id, Clase.nombre.ilike("cliente")).count() == 1


def test_respeta_la_clase_que_otro_esta_editando(equipo):
    """Beto tiene tomada la clase Pedido en el editor: la IA, trabajando para
    Ana, no la modifica; trabajando para Beto, sí."""
    db, d = equipo["db"], equipo["diagram"]
    ana, beto, _ = equipo["users"]
    DiagramToolExecutor(db, d).create_class("Pedido")
    pedido = db.query(Clase).filter(Clase.diagram_id == d.id, Clase.nombre == "Pedido").one()

    room = lock_manager._locks.setdefault(str(d.id), {})
    room[str(pedido.id)] = LockInfo(email=beto.email, ws=object())
    try:
        para_ana = DiagramToolExecutor(db, d, actor_email=ana.email)
        with pytest.raises(ToolError, match=beto.email):
            para_ana.add_attribute("Pedido", "total", "double")
        with pytest.raises(ToolError, match="editando"):
            para_ana.rename_class("Pedido", "Orden")
        # Crear clases nuevas o tocar otras sigue funcionando
        para_ana.create_class("Factura")

        para_beto = DiagramToolExecutor(db, d, actor_email=beto.email.upper())
        assert para_beto.add_attribute("Pedido", "total", "double")["ok"] is True
    finally:
        lock_manager._locks.pop(str(d.id), None)

    # Liberada la clase, la IA para Ana ya puede editarla
    assert DiagramToolExecutor(db, d, actor_email=ana.email).add_method("Pedido", "pagar")["ok"] is True


def test_renombrar_a_un_nombre_que_ya_existe(equipo):
    db, d = equipo["db"], equipo["diagram"]
    ex = DiagramToolExecutor(db, d)
    ex.create_class("Cliente")
    ex.create_class("Persona")
    with pytest.raises(ToolError, match="Ya existe"):
        ex.rename_class("Persona", "cliente")


def test_la_ia_no_edita_para_un_lector(equipo, monkeypatch):
    """Un colaborador de solo lectura puede consultar al asesor, pero la IA no
    modifica el diagrama en su nombre: la consulta va siempre en modo mentor
    (sin herramientas de edición), aunque pida un cambio."""
    db, d, users = equipo["db"], equipo["diagram"], equipo["users"]
    lector, editor = users[1], users[2]
    colab = db.query(DiagramCollaborator).filter_by(diagram_id=d.id, user_id=lector.id).one()
    colab.role = CollaboratorRole.VIEWER
    db.commit()

    modos = {}

    def _registrar(db_bg, diagram, user_text, requester=None, mode=None, **kw):
        modos[requester.name] = mode
        return AiCommandResult(reply="ok")

    monkeypatch.setattr(ai_assistant, "run_command", _registrar)
    for u in (lector, editor):
        q = chat_service.create_user_message(db, d, u, "creá la clase Factura", asks_ai=True)
        chat_service.run_ai_question_background(q.id)

    assert modos[lector.name] == ai_assistant.MODE_MENTOR
    assert modos[editor.name] is None  # el editor: se clasifica normalmente
