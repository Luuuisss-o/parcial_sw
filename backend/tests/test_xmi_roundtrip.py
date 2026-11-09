"""
CU-06: ida y vuelta XMI (exportar -> importar en un diagrama vacio) sin
perder clases, atributos (con su tipo), relaciones ni multiplicidades.

Caja negra contra el backend real (localhost:8000), como test_api_qa.py.
La compatibilidad con Enterprise Architect en si (abrir el XMI en EA) no se
puede automatizar aca: ver docs/estado-1p.md.
"""
import io

import httpx
import pytest

from exporters.generators.type_mapping import map_type

BASE_URL = "http://localhost:8000"
QA_EMAIL = "qa.tester@parcial-sw.local"
QA_PASSWORD = "TestPass123"


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE_URL, timeout=30.0,
                      limits=httpx.Limits(max_keepalive_connections=0)) as c:
        yield c


@pytest.fixture(scope="module")
def h(client):
    r = client.post("/auth/sign-in", json={"email": QA_EMAIL, "password": QA_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _diagram(client, h, title):
    r = client.post("/diagrams", json={"title": title}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _snapshot(client, h, did):
    # Estos endpoints responden con los nombres de columna en espanol
    # (nombre/atributos/tipo, origen_id/mult_origen_min...), ver
    # CONTEXTO_PROYECTO.md seccion 12.
    classes = client.get(f"/diagrams/{did}/classes", headers=h).json()
    names = {c["id"]: c["nombre"] for c in classes}
    # Se compara el tipo JAVA que usaria el backend generado: "Integer" e
    # "int" son lo mismo; "Double" y "float" no (Double -> Float pierde
    # precision), y eso es lo que importa que sobreviva.
    attrs = sorted(
        (c["nombre"], a["nombre"], map_type(a["tipo"]))
        for c in classes for a in c["atributos"]
    )
    rels = sorted(
        (names[r["origen_id"]], names[r["destino_id"]], r["tipo"],
         r["mult_origen_min"], str(r["mult_origen_max"]), r["mult_destino_min"], str(r["mult_destino_max"]))
        for r in client.get(f"/diagrams/{did}/relations", headers=h).json()
    )
    return sorted(names.values()), attrs, rels


def test_ida_y_vuelta_preserva_clases_atributos_relaciones_y_multiplicidades(client, h):
    src = _diagram(client, h, "XMI ida")
    ids = {}
    for name, attrs in {
        "Persona": [("nombre", "String")],
        "Cliente": [("email", "String"), ("activo", "Boolean")],
        "Pedido": [("fecha", "Date"), ("total", "Double"), ("descuento", "decimal"), ("codigo", "Long")],
        "DetallePedido": [("cantidad", "Integer")],
    }.items():
        ids[name] = client.post(f"/diagrams/{src}/classes", json={"name": name}, headers=h).json()["id"]
        for a, t in attrs:
            r = client.post(f"/diagrams/classes/{ids[name]}/attributes",
                            json={"name": a, "type": t, "required": False}, headers=h)
            assert r.status_code == 201, r.text

    def rel(a, b, t, **mult):
        r = client.post(f"/diagrams/{src}/relations",
                        json={"from_class": ids[a], "to_class": ids[b], "type": t, **mult}, headers=h)
        assert r.status_code == 201, r.text

    rel("Cliente", "Persona", "INHERITANCE")
    rel("Cliente", "Pedido", "ASSOCIATION", src_mult_min=1, src_mult_max=1, dst_mult_min=0, dst_mult_max="*")
    rel("DetallePedido", "Pedido", "COMPOSITION", src_mult_min=1, src_mult_max="*", dst_mult_min=1, dst_mult_max=1)

    xmi = client.get(f"/diagrams/{src}/export-xmi", headers=h)
    assert xmi.status_code == 200
    assert b"xmi:XMI" in xmi.content

    dst = _diagram(client, h, "XMI vuelta")
    r = client.post(f"/diagrams/{dst}/import-xmi", headers=h,
                    files={"file": ("modelo.xmi", io.BytesIO(xmi.content), "application/xml")})
    assert r.status_code == 200, r.text
    assert r.json()["relations_created"] == 3

    original, importado = _snapshot(client, h, src), _snapshot(client, h, dst)
    assert importado[0] == original[0], "clases"
    assert importado[1] == original[1], "atributos y tipos"
    assert importado[2] == original[2], "relaciones, tipos y multiplicidades"

    for did in (src, dst):
        client.delete(f"/diagrams/{did}", headers=h)
