"""
Suite de pruebas de caja negra: Asistente de IA (texto), Vision (foto),
XMI (import/export) y WebSocket (colaboracion en tiempo real).

Contra el backend real (localhost:8000) via docker compose, con
GEMINI_API_KEY configurada (confirmado antes de escribir esta suite).
"""
import asyncio
import io
import os
import json
import time

import httpx
import pytest
import websockets

BASE_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000"
QA_EMAIL = "qa.tester@parcial-sw.local"
QA_PASSWORD = "TestPass123"

# Llaman a Gemini de verdad: corren solo si se pide explicitamente y el
# backend tiene una GEMINI_API_KEY valida (antes estaban saltadas siempre
# porque la clave de este entorno era invalida; con una invalida dan falsos
# positivos -- la tarea en segundo plano falla en silencio).
requires_gemini = pytest.mark.skipif(
    os.environ.get("RUN_GEMINI_TESTS") != "1",
    reason="Requiere RUN_GEMINI_TESTS=1 y una GEMINI_API_KEY valida en el backend",
)


@pytest.fixture(scope="session")
def client():
    # Sin keep-alive: uvicorn cierra las conexiones ociosas a los 5 s y, si una
    # prueba lenta deja la conexion del pool vencida, la siguiente peticion
    # fallaba al azar con "Connection reset by peer" (no era un error del backend).
    limits = httpx.Limits(max_keepalive_connections=0)
    with httpx.Client(base_url=BASE_URL, timeout=30.0, limits=limits) as c:
        yield c


@pytest.fixture(scope="session")
def token(client):
    r = client.post("/auth/sign-in", json={"email": QA_EMAIL, "password": QA_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def diagram(client, auth_headers):
    r = client.post("/diagrams", json={"title": "QA - IA/Vision/XMI/WS"}, headers=auth_headers)
    assert r.status_code == 201, r.text
    d = r.json()
    yield d
    client.delete(f"/diagrams/{d['id']}", headers=auth_headers)


# ---------------------------------------------------------------------------
# A.4 Asistente inteligente (texto) -- CU-08
# ---------------------------------------------------------------------------

def test_cn_ai_001_comando_puntual_aceptado(client, auth_headers, diagram):
    r = client.post(
        f"/diagrams/{diagram['id']}/ai/command",
        json={"text": "Crea una clase llamada Factura"},
        headers=auth_headers,
    )
    assert r.status_code == 202
    assert r.json()["status"] == "processing"


@requires_gemini
def test_cn_ai_001b_comando_se_ejecuta_realmente(client, auth_headers, diagram):
    """Verifica de punta a punta: el comando en lenguaje natural termina
    creando una clase real en la base, no solo aceptando la request."""
    r = client.post(
        f"/diagrams/{diagram['id']}/ai/command",
        json={"text": "Crea una clase llamada ClaseCreadaPorIA"},
        headers=auth_headers,
    )
    assert r.status_code == 202

    # El comando se procesa en background (BackgroundTasks); se hace polling
    # sobre /classes hasta ver la clase aparecer o agotar el timeout.
    deadline = time.time() + 20
    encontrada = False
    while time.time() < deadline:
        clases = client.get(f"/diagrams/{diagram['id']}/classes", headers=auth_headers).json()
        if any(c["nombre"] == "ClaseCreadaPorIA" for c in clases):
            encontrada = True
            break
        time.sleep(1)
    assert encontrada, "La clase no aparecio via la API tras 20s de espera al asistente de IA"


@requires_gemini
def test_cn_ai_002_rechaza_diseno_completo_sin_clases_concretas(client, auth_headers, diagram):
    """Regla de la catedra: el asistente no debe generar un diagrama completo
    desde una descripcion abierta. Se verifica que, tras el comando, NO se
    hayan creado multiples clases nuevas (mas de las que ya existian)."""
    antes = client.get(f"/diagrams/{diagram['id']}/classes", headers=auth_headers).json()
    r = client.post(
        f"/diagrams/{diagram['id']}/ai/command",
        json={"text": "Disename un sistema completo de facturacion con todas sus clases"},
        headers=auth_headers,
    )
    assert r.status_code == 202
    time.sleep(8)  # tiempo suficiente para que Gemini responda y se procese
    despues = client.get(f"/diagrams/{diagram['id']}/classes", headers=auth_headers).json()
    assert len(despues) == len(antes), (
        "El asistente creo clases nuevas ante una descripcion abierta de negocio; "
        "deberia haberse negado segun el SYSTEM_PROMPT."
    )


# ---------------------------------------------------------------------------
# A.5 Importacion desde fotografia -- CU-09
# ---------------------------------------------------------------------------

@requires_gemini
def test_cn_vision_002_imagen_sin_contenido_reconocible(client, auth_headers):
    """Una imagen 1x1 en blanco no deberia contener ninguna clase UML."""
    # PNG 1x1 blanco valido, generado a mano (bytes minimos de un PNG real).
    png_1x1 = bytes.fromhex(
        "89504e470d0a1a0a0000000d494844520000000100000001080600000"
        "01f15c4890000000a49444154789c6360000002000155273de50000000049454e44ae426082"
    )
    files = {"file": ("blank.png", io.BytesIO(png_1x1), "image/png")}
    r = client.post("/vision/detect", files=files, headers=auth_headers)
    assert r.status_code == 422
    assert "no se reconoci" in r.json()["detail"].lower() or r.json()["detail"]


def test_cn_vision_004_mimetype_no_soportado(client, auth_headers):
    files = {"file": ("doc.txt", io.BytesIO(b"esto no es una imagen"), "text/plain")}
    r = client.post("/vision/detect", files=files, headers=auth_headers)
    assert r.status_code == 400
    assert "imagen" in r.json()["detail"].lower()


def test_cn_vision_005_apply_sin_clases(client, auth_headers):
    r = client.post(
        "/vision/apply",
        json={"title": "vacio", "classes": [], "relations": []},
        headers=auth_headers,
    )
    assert r.status_code == 400
    assert "no hay ninguna clase" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# A.6 Interoperabilidad XMI -- CU-10
# ---------------------------------------------------------------------------

def test_cn_xmi_001_exportar_diagrama(client, auth_headers, diagram):
    client.post(f"/diagrams/{diagram['id']}/classes", json={"name": "Producto"}, headers=auth_headers)
    r = client.get(f"/diagrams/{diagram['id']}/export-xmi", headers=auth_headers)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/xml"
    assert b"<?xml" in r.content
    assert b"uml:Class" in r.content
    assert b"Producto" in r.content


def test_cn_xmi_002_importar_xmi_valido_con_clase_y_relacion(client, auth_headers, diagram):
    xmi_content = b'''<?xml version="1.0" encoding="UTF-8"?>
<xmi:XMI xmi:version="2.1" xmlns:xmi="http://schema.omg.org/spec/XMI/2.1" xmlns:uml="http://schema.omg.org/spec/UML/2.1">
  <uml:Model xmi:id="model_1" name="ImportadoQA">
    <packagedElement xmi:type="uml:Class" xmi:id="C_1" name="Empleado">
      <ownedAttribute xmi:type="uml:Property" xmi:id="A_1" name="legajo">
        <type xmi:type="uml:PrimitiveType" href="http://schema.omg.org/spec/UML/2.1/uml.xml#Integer"/>
      </ownedAttribute>
    </packagedElement>
    <packagedElement xmi:type="uml:Class" xmi:id="C_2" name="Departamento"/>
  </uml:Model>
</xmi:XMI>'''
    files = {"file": ("importado.xmi", io.BytesIO(xmi_content), "application/xml")}
    r = client.post(f"/diagrams/{diagram['id']}/import-xmi", files=files, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert "Empleado" in body["classes_created"]
    assert "Departamento" in body["classes_created"]
    assert body["attributes_created"] == 1


def test_cn_xmi_003_reimportar_mismo_xmi_es_idempotente(client, auth_headers, diagram):
    xmi_content = b'''<?xml version="1.0" encoding="UTF-8"?>
<xmi:XMI xmi:version="2.1" xmlns:xmi="http://schema.omg.org/spec/XMI/2.1" xmlns:uml="http://schema.omg.org/spec/UML/2.1">
  <uml:Model xmi:id="model_1" name="Idempotente">
    <packagedElement xmi:type="uml:Class" xmi:id="C_1" name="Reintento"/>
  </uml:Model>
</xmi:XMI>'''
    files1 = {"file": ("dup.xmi", io.BytesIO(xmi_content), "application/xml")}
    r1 = client.post(f"/diagrams/{diagram['id']}/import-xmi", files=files1, headers=auth_headers)
    assert r1.status_code == 200
    assert "Reintento" in r1.json()["classes_created"]

    files2 = {"file": ("dup.xmi", io.BytesIO(xmi_content), "application/xml")}
    r2 = client.post(f"/diagrams/{diagram['id']}/import-xmi", files=files2, headers=auth_headers)
    assert r2.status_code == 200
    body2 = r2.json()
    assert "Reintento" in body2["classes_skipped"]
    assert "Reintento" not in body2["classes_created"]


def test_cn_xmi_004_archivo_no_es_xml_valido(client, auth_headers, diagram):
    files = {"file": ("roto.xmi", io.BytesIO(b"esto no es xml{{{"), "application/xml")}
    r = client.post(f"/diagrams/{diagram['id']}/import-xmi", files=files, headers=auth_headers)
    assert r.status_code == 400


def test_cn_xmi_005_archivo_vacio(client, auth_headers, diagram):
    files = {"file": ("vacio.xmi", io.BytesIO(b""), "application/xml")}
    r = client.post(f"/diagrams/{diagram['id']}/import-xmi", files=files, headers=auth_headers)
    assert r.status_code == 400
    assert "vacio" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# A.8 Colaboracion mediante WebSocket -- CU-12
# ---------------------------------------------------------------------------

def test_cn_ws_001_handshake_con_token_valido(client, auth_headers, diagram, token):
    async def _run():
        uri = f"{WS_URL}/diagrams/{diagram['id']}/ws?token={token}"
        async with websockets.connect(uri) as ws:
            first = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            assert first["event"] == "connected"
            assert "conn_id" in first["data"]
            second = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            assert second["event"] == "locks.snapshot"

    asyncio.run(_run())


def test_cn_ws_002_conexion_rechazada_sin_token(diagram):
    # El rechazo ocurre durante el handshake HTTP de upgrade (antes de
    # completar la conexion WS), por lo que websockets lo reporta como un
    # InvalidStatus 403, no como un cierre posterior a la conexion.
    async def _run():
        uri = f"{WS_URL}/diagrams/{diagram['id']}/ws"
        with pytest.raises(websockets.exceptions.InvalidStatus) as exc_info:
            async with websockets.connect(uri):
                pass
        assert exc_info.value.response.status_code == 403

    asyncio.run(_run())


async def _recv_event(ws, event, timeout=5):
    """Devuelve el proximo mensaje `event`, ignorando los demas (presence,
    cursores, etc.): desde la Fase 2 el servidor manda "presence" al entrar
    alguien, y estas pruebas leian el siguiente mensaje a ciegas."""
    async def _loop():
        while True:
            msg = json.loads(await ws.recv())
            if msg.get("event") == event:
                return msg
    return await asyncio.wait_for(_loop(), timeout=timeout)


def test_cn_ws_003_lock_y_broadcast_entre_dos_conexiones(client, auth_headers, diagram, token):
    """Usuario A bloquea una clase; Usuario B (misma cuenta, otra conexion,
    simulando otra pestana) debe recibir el evento class.locked."""
    clase = client.post(f"/diagrams/{diagram['id']}/classes", json={"name": "ClaseParaLock"}, headers=auth_headers).json()

    async def _run():
        uri = f"{WS_URL}/diagrams/{diagram['id']}/ws?token={token}"
        async with websockets.connect(uri) as ws_a, websockets.connect(uri) as ws_b:
            for ws in (ws_a, ws_b):
                await _recv_event(ws, "locks.snapshot")

            await ws_a.send(json.dumps({"action": "lock", "class_id": clase["id"]}))

            # ws_a tambien recibe el broadcast (el server no se auto-excluye
            # para eventos de lock, a diferencia de cursor.move).
            evt_a = await _recv_event(ws_a, "class.locked")
            evt_b = await _recv_event(ws_b, "class.locked")
            assert evt_a["event"] == "class.locked"
            assert evt_b["event"] == "class.locked"
            assert evt_a["data"]["class_id"] == clase["id"]

    asyncio.run(_run())


def test_cn_ws_004_lock_denegado_a_segunda_conexion(client, auth_headers, diagram, token):
    clase = client.post(f"/diagrams/{diagram['id']}/classes", json={"name": "ClaseDobleLock"}, headers=auth_headers).json()

    async def _run():
        uri = f"{WS_URL}/diagrams/{diagram['id']}/ws?token={token}"
        async with websockets.connect(uri) as ws_a, websockets.connect(uri) as ws_b:
            for ws in (ws_a, ws_b):
                await _recv_event(ws, "locks.snapshot")

            await ws_a.send(json.dumps({"action": "lock", "class_id": clase["id"]}))
            await _recv_event(ws_a, "class.locked")
            await _recv_event(ws_b, "class.locked")

            await ws_b.send(json.dumps({"action": "lock", "class_id": clase["id"]}))
            evt = await _recv_event(ws_b, "lock.denied")
            assert evt["event"] == "lock.denied"
            assert evt["data"]["class_id"] == clase["id"]

    asyncio.run(_run())


def test_cn_ws_005_ping_responde_pong_solo_a_quien_lo_manda(client, auth_headers, diagram, token):
    """Keepalive: nginx corta el WebSocket tras 100 s sin trafico; el cliente
    manda ping cada 25 s y el servidor contesta pong (sin difundirlo)."""
    async def _run():
        uri = f"{WS_URL}/diagrams/{diagram['id']}/ws?token={token}"
        async with websockets.connect(uri) as ws_a, websockets.connect(uri) as ws_b:
            for ws in (ws_a, ws_b):
                await _recv_event(ws, "locks.snapshot")
            await ws_a.send(json.dumps({"action": "ping"}))
            assert (await _recv_event(ws_a, "pong"))["event"] == "pong"
            with pytest.raises(asyncio.TimeoutError):
                await _recv_event(ws_b, "pong", timeout=1.5)

    asyncio.run(_run())
