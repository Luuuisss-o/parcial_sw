"""
Suite de pruebas de caja negra contra el backend real (localhost:8000),
levantado via docker compose. Requiere que el usuario de QA exista en la
base (ver docs/contexto o el registro de esta sesion):

    email: qa.tester@parcial-sw.local
    password: TestPass123

No modifica ningun archivo de codigo del proyecto. Solo consume la API.
"""
import httpx
import pytest

BASE_URL = "http://localhost:8000"
QA_EMAIL = "qa.tester@parcial-sw.local"
QA_PASSWORD = "TestPass123"


@pytest.fixture(scope="session")
def client():
    with httpx.Client(base_url=BASE_URL, timeout=15.0) as c:
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
    r = client.post("/diagrams", json={"title": "QA - Diagrama de prueba"}, headers=auth_headers)
    assert r.status_code == 201, r.text
    d = r.json()
    yield d
    client.delete(f"/diagrams/{d['id']}", headers=auth_headers)


# ---------------------------------------------------------------------------
# A.1 Autenticacion
# ---------------------------------------------------------------------------

def test_cn_auth_001_login_exitoso(client):
    r = client.post("/auth/sign-in", json={"email": QA_EMAIL, "password": QA_PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body and body["access_token"]


def test_cn_auth_002_password_incorrecta(client):
    r = client.post("/auth/sign-in", json={"email": QA_EMAIL, "password": "incorrecta"})
    assert r.status_code == 400


def test_cn_auth_003_sin_token(client):
    r = client.get("/diagrams")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# A.2 Gestion de diagramas
# ---------------------------------------------------------------------------

def test_cn_diag_001_crear_diagrama(client, auth_headers):
    r = client.post("/diagrams", json={"title": "QA - crear"}, headers=auth_headers)
    assert r.status_code == 201
    body = r.json()
    assert body["title"] == "QA - crear"
    client.delete(f"/diagrams/{body['id']}", headers=auth_headers)


def test_cn_diag_002_listar_diagramas(client, auth_headers):
    r = client.get("/diagrams", params={"page": 1, "limit": 20}, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert "items" in body and "total" in body


def test_cn_diag_004_diagrama_inexistente(client, auth_headers):
    r = client.get("/diagrams/00000000-0000-0000-0000-000000000000", headers=auth_headers)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# A.3 Elementos UML
# ---------------------------------------------------------------------------

def test_cn_uml_001_crear_clase(client, auth_headers, diagram):
    r = client.post(f"/diagrams/{diagram['id']}/classes", json={"name": "Cliente"}, headers=auth_headers)
    assert r.status_code == 201
    # El output real usa "nombre" (ORM en espanol), no "name" (input en ingles):
    # inconsistencia de nombres ya documentada en CONTEXTO_PROYECTO.md.
    assert r.json()["nombre"] == "Cliente"


def test_cn_uml_002_clase_duplicada(client, auth_headers, diagram):
    client.post(f"/diagrams/{diagram['id']}/classes", json={"name": "Producto"}, headers=auth_headers)
    r = client.post(f"/diagrams/{diagram['id']}/classes", json={"name": "Producto"}, headers=auth_headers)
    assert r.status_code == 400
    assert "ya existe" in r.json()["detail"]


def test_cn_uml_004_atributo_duplicado(client, auth_headers, diagram):
    c = client.post(f"/diagrams/{diagram['id']}/classes", json={"name": "Orden"}, headers=auth_headers).json()
    client.post(f"/diagrams/classes/{c['id']}/attributes", json={"name": "total", "type": "float", "required": True}, headers=auth_headers)
    r = client.post(f"/diagrams/classes/{c['id']}/attributes", json={"name": "total", "type": "int", "required": False}, headers=auth_headers)
    assert r.status_code == 400
    assert "ya tiene un atributo" in r.json()["detail"]


def test_cn_uml_006_herencia_fuerza_multiplicidad_1a1(client, auth_headers, diagram):
    padre = client.post(f"/diagrams/{diagram['id']}/classes", json={"name": "Vehiculo"}, headers=auth_headers).json()
    hijo = client.post(f"/diagrams/{diagram['id']}/classes", json={"name": "Auto"}, headers=auth_headers).json()
    r = client.post(
        f"/diagrams/{diagram['id']}/relations",
        json={
            "from_class": hijo["id"], "to_class": padre["id"], "type": "INHERITANCE",
            "src_mult_max": 5, "dst_mult_max": 5,
        },
        headers=auth_headers,
    )
    assert r.status_code == 201
    body = r.json()
    # RelacionOut usa los alias reales del ORM (mult_origen_*/mult_destino_*),
    # no los nombres de input (src_mult_*/dst_mult_*).
    assert body["mult_origen_min"] == 1 and body["mult_origen_max"] == 1
    assert body["mult_destino_min"] == 1 and body["mult_destino_max"] == 1


# ---------------------------------------------------------------------------
# A.7 Exportacion Spring Boot (hallazgo de seguridad)
# ---------------------------------------------------------------------------

def test_cn_exp_004_export_sin_auth(client, auth_headers, diagram):
    # El validador exige al menos una clase en el diagrama antes de exportar
    # ("El diagrama debe tener al menos una clase."); se agrega para aislar
    # la variable real bajo prueba: la ausencia de header Authorization.
    client.post(f"/diagrams/{diagram['id']}/classes", json={"name": "ClaseParaExportar"}, headers=auth_headers)
    r = client.post(f"/diagrams/{diagram['id']}/export-download")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"


def test_cn_exp_002_export_diagrama_inexistente(client):
    r = client.post("/diagrams/00000000-0000-0000-0000-000000000000/export-download")
    assert r.status_code == 404
