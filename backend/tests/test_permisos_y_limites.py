"""
Permisos de los colaboradores y límite de intentos de acceso.

- Un colaborador de SOLO LECTURA ve el diagrama, el chat y puede exportar,
  pero no puede modificar nada (antes el rol se elegía al invitar y no se
  aplicaba: el lector editaba igual). Pasado a editor, puede.
- Inicio de sesión: tras varios intentos fallidos con un correo desde una
  misma IP, se bloquea un rato (aunque la contraseña sea la correcta); otra
  IP no se ve afectada. Registro: tope de cuentas nuevas por IP por hora.

Caja negra contra el backend real (localhost:8000). Cada prueba usa su propia
IP (X-Real-IP, que en producción pone el nginx) para no sumar intentos a
las demás. Las cuentas creadas (@permisos.test) se borran al final.
"""
import io
import random
import uuid

import httpx
import pytest

BASE_URL = "http://localhost:8000"
PASS = "Clave1234"


def _ip():
    return f"10.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}"


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE_URL, timeout=30.0,
                      limits=httpx.Limits(max_keepalive_connections=0)) as c:
        yield c
    from app.db import SessionLocal
    from app.models.user import User
    db = SessionLocal()
    db.query(User).filter(User.email.like("%@permisos.test")).delete(synchronize_session=False)
    db.commit()
    db.close()


def _cuenta(client, nombre):
    email = f"{nombre.lower()}.{uuid.uuid4().hex[:6]}@permisos.test"
    r = client.post("/auth/sign-up", json={"name": nombre, "email": email, "password": PASS},
                    headers={"X-Real-IP": _ip()})
    assert r.status_code == 201, r.text
    return email, {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def equipo(client):
    """Dueño con un diagrama (Cliente con un atributo, Pedido y una relación)
    y un colaborador de solo lectura."""
    _, dueno = _cuenta(client, "Duena")
    lector_email, lector = _cuenta(client, "Lector")
    did = client.post("/diagrams", json={"title": "Permisos"}, headers=dueno).json()["id"]
    cid = client.post(f"/diagrams/{did}/classes", json={"name": "Cliente"}, headers=dueno).json()["id"]
    pid = client.post(f"/diagrams/{did}/classes", json={"name": "Pedido"}, headers=dueno).json()["id"]
    aid = client.post(f"/diagrams/classes/{cid}/attributes",
                      json={"name": "email", "type": "string"}, headers=dueno).json()["id"]
    rid = client.post(f"/diagrams/{did}/relations", json={"from_class": pid, "to_class": cid,
                                                          "type": "ASSOCIATION"}, headers=dueno).json()["id"]
    r = client.post(f"/diagrams/{did}/collaborators", json={"email": lector_email, "role": "VIEWER"},
                    headers=dueno)
    assert r.status_code == 201, r.text
    return {"did": did, "cid": cid, "pid": pid, "aid": aid, "rid": rid,
            "dueno": dueno, "lector": lector, "lector_email": lector_email}


def test_el_lector_ve_su_rol_y_el_diagrama(client, equipo):
    did, lector = equipo["did"], equipo["lector"]
    d = client.get(f"/diagrams/{did}", headers=lector).json()
    assert d["my_role"] == "VIEWER"
    assert client.get(f"/diagrams/{did}", headers=equipo["dueno"]).json()["my_role"] == "OWNER"
    lista = client.get("/diagrams", headers=lector).json()["items"]
    assert [x["my_role"] for x in lista if x["id"] == did] == ["VIEWER"]
    # Puede leer todo y exportar
    assert client.get(f"/diagrams/{did}/classes", headers=lector).status_code == 200
    assert client.get(f"/diagrams/{did}/relations", headers=lector).status_code == 200
    assert client.get(f"/diagrams/{did}/export-xmi", headers=lector).status_code == 200
    # Y usar el chat del equipo
    assert client.post(f"/diagrams/{did}/chat", json={"text": "hola equipo"}, headers=lector).status_code == 201


@pytest.mark.parametrize("metodo,ruta,cuerpo", [
    ("post", "/diagrams/{did}/classes", {"name": "Intrusa"}),
    ("patch", "/diagrams/classes/{cid}", {"name": "Renombrada"}),
    ("patch", "/diagrams/classes/{cid}", {"x_grid": 40}),
    ("delete", "/diagrams/classes/{pid}", None),
    ("post", "/diagrams/classes/{cid}/attributes", {"name": "nuevo", "type": "string"}),
    ("patch", "/diagrams/attributes/{aid}", {"name": "otro"}),
    ("delete", "/diagrams/attributes/{aid}", None),
    ("post", "/diagrams/classes/{cid}/methods", {"name": "op"}),
    ("post", "/diagrams/{did}/relations", {"from_class": "{cid}", "to_class": "{pid}", "type": "DEPENDENCY"}),
    ("patch", "/diagrams/relations/{rid}", {"label": "x"}),
    ("delete", "/diagrams/relations/{rid}", None),
])
def test_el_lector_no_puede_modificar(client, equipo, metodo, ruta, cuerpo):
    url = ruta.format(**equipo)
    if cuerpo:
        cuerpo = {k: (v.format(**equipo) if isinstance(v, str) else v) for k, v in cuerpo.items()}
    r = client.request(metodo.upper(), url, json=cuerpo, headers=equipo["lector"])
    assert r.status_code == 403, r.text
    assert "solo lectura" in r.json()["detail"]


def test_el_lector_no_puede_importar_xmi(client, equipo):
    xmi = client.get(f"/diagrams/{equipo['did']}/export-xmi", headers=equipo["dueno"]).content
    r = client.post(f"/diagrams/{equipo['did']}/import-xmi", headers=equipo["lector"],
                    files={"file": ("x.xmi", io.BytesIO(xmi), "application/xml")})
    assert r.status_code == 403


def test_nada_cambio_y_como_editor_si_puede(client, equipo):
    did, dueno, lector = equipo["did"], equipo["dueno"], equipo["lector"]
    nombres = sorted(c["nombre"] for c in client.get(f"/diagrams/{did}/classes", headers=dueno).json())
    assert nombres == ["Cliente", "Pedido"]

    r = client.post(f"/diagrams/{did}/collaborators", json={"email": equipo["lector_email"], "role": "EDITOR"},
                    headers=dueno)
    assert r.status_code in (200, 201), r.text
    assert client.get(f"/diagrams/{did}", headers=lector).json()["my_role"] == "EDITOR"
    r = client.post(f"/diagrams/{did}/classes", json={"name": "Factura"}, headers=lector)
    assert r.status_code == 201, r.text


# ---------------------------------------------------------------- límite de intentos
def test_bloqueo_por_intentos_fallidos(client):
    email, _ = _cuenta(client, "Victima")
    ip = _ip()
    h = {"X-Real-IP": ip}
    for _ in range(8):
        r = client.post("/auth/sign-in", json={"email": email, "password": "mala-clave"}, headers=h)
        assert r.status_code == 400
    # Agotados: ni siquiera la contraseña correcta entra desde esa IP
    r = client.post("/auth/sign-in", json={"email": email, "password": PASS}, headers=h)
    assert r.status_code == 429 and "Demasiados intentos" in r.json()["detail"]
    assert int(r.headers["Retry-After"]) > 0
    # Desde otra IP, el dueño de la cuenta entra normal
    r = client.post("/auth/sign-in", json={"email": email, "password": PASS}, headers={"X-Real-IP": _ip()})
    assert r.status_code == 200


def test_un_ingreso_correcto_reinicia_el_contador(client):
    email, _ = _cuenta(client, "Distraida")
    h = {"X-Real-IP": _ip()}
    for _ in range(5):
        client.post("/auth/sign-in", json={"email": email, "password": "mala-clave"}, headers=h)
    assert client.post("/auth/sign-in", json={"email": email, "password": PASS}, headers=h).status_code == 200
    for _ in range(5):
        assert client.post("/auth/sign-in", json={"email": email, "password": "mala-clave"},
                           headers=h).status_code == 400


def test_tope_de_cuentas_nuevas_por_ip(client):
    h = {"X-Real-IP": _ip()}
    for i in range(10):
        r = client.post("/auth/sign-up", json={"name": "Serie", "email": f"serie{i}.{uuid.uuid4().hex[:4]}@permisos.test",
                                                "password": PASS}, headers=h)
        assert r.status_code == 201, r.text
    r = client.post("/auth/sign-up", json={"name": "Serie", "email": f"once.{uuid.uuid4().hex[:4]}@permisos.test",
                                            "password": PASS}, headers=h)
    assert r.status_code == 429 and "demasiadas cuentas" in r.json()["detail"]
