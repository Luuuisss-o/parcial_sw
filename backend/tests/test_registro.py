"""
Registro de usuarios desde el login (POST /auth/sign-up).

Caja negra contra el backend real (localhost:8000), como test_api_qa.py.
Las cuentas que crea usan el dominio @registro.test y se borran al final.
"""
import uuid

import httpx
import pytest

BASE_URL = "http://localhost:8000"


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE_URL, timeout=30.0,
                      limits=httpx.Limits(max_keepalive_connections=0)) as c:
        yield c
    # Limpieza: las cuentas de prueba no quedan en la base.
    from app.db import SessionLocal
    from app.models.user import User
    db = SessionLocal()
    db.query(User).filter(User.email.like("%@registro.test")).delete(synchronize_session=False)
    db.commit()
    db.close()


def _email():
    return f"nuevo.{uuid.uuid4().hex[:8]}@registro.test"


def test_registro_crea_la_cuenta_y_deja_la_sesion_iniciada(client):
    email = _email()
    r = client.post("/auth/sign-up", json={"name": "  Ana   Pérez ", "email": email.upper(), "password": "Clave1234"})
    assert r.status_code == 201, r.text
    token = r.json()["access_token"]

    # El token sirve: puede crear y listar sus diagramas.
    h = {"Authorization": f"Bearer {token}"}
    d = client.post("/diagrams", json={"title": "Mi primer diagrama"}, headers=h)
    assert d.status_code == 201, d.text
    assert any(x["title"] == "Mi primer diagrama" for x in client.get("/diagrams", headers=h).json()["items"])

    # Y puede volver a entrar con su correo (en cualquier mayúscula) y clave.
    r = client.post("/auth/sign-in", json={"email": email.title(), "password": "Clave1234"})
    assert r.status_code == 200, r.text

    from app.db import SessionLocal
    from app.models.user import User
    db = SessionLocal()
    u = db.query(User).filter(User.email == email).one()
    assert u.name == "Ana Pérez" and u.role.value == "editor" and u.active
    assert u.password_hash != "Clave1234"  # guardada con hash, nunca en texto plano
    db.close()


def test_correo_repetido(client):
    email = _email()
    assert client.post("/auth/sign-up", json={"name": "Beto", "email": email, "password": "Clave1234"}).status_code == 201
    r = client.post("/auth/sign-up", json={"name": "Otro", "email": email.upper(), "password": "OtraClave99"})
    assert r.status_code == 409
    assert "Ya existe una cuenta" in r.json()["detail"]


@pytest.mark.parametrize("body,mensaje", [
    ({"name": "A", "email": "x@registro.test", "password": "Clave1234"}, "nombre"),
    ({"name": "Ana", "email": "no-es-un-correo", "password": "Clave1234"}, "correo"),
    ({"name": "Ana", "email": "ana@registro", "password": "Clave1234"}, "correo"),
    ({"name": "Ana", "email": "ana2@registro.test", "password": "corta"}, "al menos 8"),
    ({"name": "Ana", "email": "ana3@registro.test", "password": " clave1234 "}, "espacios"),
])
def test_datos_invalidos(client, body, mensaje):
    r = client.post("/auth/sign-up", json=body)
    assert r.status_code == 400
    assert mensaje in r.json()["detail"]


def test_dos_altas_simultaneas_con_el_mismo_correo_crean_una_sola_cuenta(client):
    """El índice único de la base frena la carrera aunque las dos pasen el
    chequeo previo del endpoint."""
    import threading
    email = _email()
    codes = []

    def alta():
        with httpx.Client(base_url=BASE_URL, timeout=30.0) as c:
            codes.append(c.post("/auth/sign-up", json={"name": "Caro", "email": email,
                                                         "password": "Clave1234"}).status_code)

    hilos = [threading.Thread(target=alta) for _ in range(5)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert sorted(codes).count(201) == 1 and codes.count(409) == 4

    from app.db import SessionLocal
    from app.models.user import User
    from sqlalchemy import func
    db = SessionLocal()
    assert db.query(User).filter(func.lower(User.email) == email).count() == 1
    db.close()
