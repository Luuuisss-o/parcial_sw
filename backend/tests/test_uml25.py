"""
Notación UML 2.5 del diagrama de clases: tipos de clase (abstracta,
interfaz, enumeración), visibilidad, miembros estáticos/derivados/abstractos,
multiplicidad y valor inicial de atributos, parámetros de operaciones,
realización de interfaces, roles y navegabilidad de las asociaciones.

Caja negra contra el backend real (localhost:8000), como test_api_qa.py.
Incluye la ida y vuelta por XMI (nada de esto se pierde al exportar e
importar) y que el generador de código no trate interfaces/enumeraciones
como entidades.
"""
import io
import zipfile

import httpx
import pytest

BASE_URL = "http://localhost:8000"
QA_EMAIL = "qa.tester@parcial-sw.local"
QA_PASSWORD = "TestPass123"


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE_URL, timeout=60.0,
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


def _class(client, h, did, name, kind="class"):
    r = client.post(f"/diagrams/{did}/classes", json={"name": name, "kind": kind}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture(scope="module")
def modelo(client, h):
    """Pagable (interfaz) <- Pedido (abstracta) -> Cliente, más EstadoPedido
    (enumeración), con toda la notación cargada."""
    did = _diagram(client, h, "UML 2.5 - notación")
    pagable = _class(client, h, did, "Pagable", "interface")
    pedido = _class(client, h, did, "Pedido", "abstract")
    cliente = _class(client, h, did, "Cliente")
    estado = _class(client, h, did, "EstadoPedido", "enumeration")

    for lit in ("PENDIENTE", "PAGADO"):
        r = client.post(f"/diagrams/classes/{estado}/attributes",
                        json={"name": lit, "type": "string", "visibility": "+"}, headers=h)
        assert r.status_code == 201, r.text

    r = client.post(f"/diagrams/classes/{pedido}/attributes", json={
        "name": "items", "type": "string", "visibility": "#",
        "multiplicity": "[1..*]", "default_value": " vacio ",
    }, headers=h)
    assert r.status_code == 201, r.text
    attr_items = r.json()
    r = client.post(f"/diagrams/classes/{pedido}/attributes", json={
        "name": "total", "type": "double", "is_derived": True,
    }, headers=h)
    assert r.status_code == 201, r.text
    r = client.post(f"/diagrams/classes/{pedido}/attributes", json={
        "name": "contador", "type": "int", "is_static": True, "visibility": "+",
    }, headers=h)
    assert r.status_code == 201, r.text

    r = client.post(f"/diagrams/classes/{pedido}/methods", json={
        "name": "calcularTotal", "return_type": "double", "is_abstract": True,
        "params": "(descuento: double, cupon: string)",
    }, headers=h)
    assert r.status_code == 201, r.text
    meth = r.json()
    r = client.post(f"/diagrams/classes/{pagable}/methods", json={
        "name": "pagar", "return_type": "boolean", "visibility": "+", "is_abstract": True,
    }, headers=h)
    assert r.status_code == 201, r.text
    r = client.post(f"/diagrams/classes/{cliente}/methods", json={
        "name": "crear", "return_type": "Cliente", "is_static": True, "params": "nombre: string",
    }, headers=h)
    assert r.status_code == 201, r.text

    r = client.post(f"/diagrams/{did}/relations", json={
        "from_class": pedido, "to_class": pagable, "type": "REALIZATION",
        "src_role": "no aplica", "src_navigable": True,
    }, headers=h)
    assert r.status_code == 201, r.text
    realizacion = r.json()
    r = client.post(f"/diagrams/{did}/relations", json={
        "from_class": pedido, "to_class": cliente, "type": "ASSOCIATION",
        "src_mult_min": 0, "src_mult_max": "*", "dst_mult_min": 1, "dst_mult_max": 1,
        "src_role": " pedidos ", "dst_role": "comprador",
        "dst_navigable": True,
    }, headers=h)
    assert r.status_code == 201, r.text
    asociacion = r.json()
    return {
        "did": did, "pagable": pagable, "pedido": pedido, "cliente": cliente, "estado": estado,
        "attr_items": attr_items, "meth": meth, "realizacion": realizacion, "asociacion": asociacion,
    }


# ---------------------------------------------------------------- API
def test_tipos_de_clase(client, h, modelo):
    clases = {c["nombre"]: c for c in client.get(f"/diagrams/{modelo['did']}/classes", headers=h).json()}
    assert clases["Pagable"]["tipo_clase"] == "interface"
    assert clases["Pedido"]["tipo_clase"] == "abstract"
    assert clases["Cliente"]["tipo_clase"] == "class"
    assert clases["EstadoPedido"]["tipo_clase"] == "enumeration"

    r = client.patch(f"/diagrams/classes/{modelo['cliente']}", json={"kind": "abstract"}, headers=h)
    assert r.status_code == 200 and r.json()["tipo_clase"] == "abstract"
    r = client.patch(f"/diagrams/classes/{modelo['cliente']}", json={"kind": "class"}, headers=h)
    assert r.json()["tipo_clase"] == "class"

    r = client.post(f"/diagrams/{modelo['did']}/classes", json={"name": "X", "kind": "struct"}, headers=h)
    assert r.status_code == 422


def test_atributo_con_notacion_completa(client, h, modelo):
    a = modelo["attr_items"]
    assert a["visibility"] == "#"
    assert a["multiplicity"] == "1..*"  # se aceptan los corchetes y se guardan sin ellos
    assert a["default_value"] == "vacio"
    assert a["is_static"] is False and a["is_derived"] is False

    attrs = {x["name"]: x for x in client.get(f"/diagrams/classes/{modelo['pedido']}/attributes", headers=h).json()}
    assert attrs["total"]["is_derived"] is True
    assert attrs["contador"]["is_static"] is True and attrs["contador"]["visibility"] == "+"
    # Sin indicar visibilidad, un atributo es privado (convención UML habitual)
    assert attrs["total"]["visibility"] == "-"


def test_editar_y_borrar_multiplicidad_de_atributo(client, h, modelo):
    aid = modelo["attr_items"]["id"]
    r = client.patch(f"/diagrams/attributes/{aid}", json={"multiplicity": "0..5", "is_static": True}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["multiplicity"] == "0..5" and r.json()["is_static"] is True

    # Un PATCH sin el campo no lo toca; "" lo borra.
    r = client.patch(f"/diagrams/attributes/{aid}", json={"type": "text"}, headers=h)
    assert r.json()["multiplicity"] == "0..5"
    r = client.patch(f"/diagrams/attributes/{aid}", json={"multiplicity": "", "default_value": "", "is_static": False}, headers=h)
    assert r.json()["multiplicity"] is None and r.json()["default_value"] is None


@pytest.mark.parametrize("mult", ["5..2", "*..3", "uno", "1..2..3"])
def test_multiplicidad_invalida(client, h, modelo, mult):
    r = client.post(f"/diagrams/classes/{modelo['cliente']}/attributes",
                    json={"name": f"m{abs(hash(mult))}", "type": "string", "multiplicity": mult}, headers=h)
    assert r.status_code == 422


def test_visibilidad_invalida(client, h, modelo):
    r = client.post(f"/diagrams/classes/{modelo['cliente']}/attributes",
                    json={"name": "malo", "type": "string", "visibility": "public"}, headers=h)
    assert r.status_code == 422


def test_metodo_con_parametros(client, h, modelo):
    m = modelo["meth"]
    assert m["params"] == "descuento: double, cupon: string"  # sin los paréntesis
    assert m["is_abstract"] is True and m["visibility"] == "+"

    r = client.patch(f"/diagrams/methods/{m['id']}", json={"visibility": "~", "params": ""}, headers=h)
    assert r.status_code == 200
    assert r.json()["visibility"] == "~" and r.json()["params"] == ""
    r = client.patch(f"/diagrams/methods/{m['id']}",
                     json={"visibility": "+", "params": "descuento: double, cupon: string"}, headers=h)
    assert r.json()["params"] == "descuento: double, cupon: string"


def test_realizacion_sin_roles_ni_multiplicidad(modelo):
    r = modelo["realizacion"]
    assert r["tipo"] == "REALIZATION"
    assert r["rol_origen"] is None and r["navegable_origen"] is False
    assert r["mult_origen_min"] == 1 and r["mult_destino_max"] == 1


def test_asociacion_con_roles_y_navegabilidad(client, h, modelo):
    a = modelo["asociacion"]
    assert a["rol_origen"] == "pedidos" and a["rol_destino"] == "comprador"
    assert a["navegable_destino"] is True and a["navegable_origen"] is False

    det = client.get(f"/diagrams/relations/{a['id']}", headers=h).json()
    assert det["src_role"] == "pedidos" and det["dst_navigable"] is True

    r = client.patch(f"/diagrams/relations/{a['id']}", json={"src_navigable": True, "dst_role": ""}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["navegable_origen"] is True and r.json()["rol_destino"] is None
    r = client.patch(f"/diagrams/relations/{a['id']}",
                     json={"src_navigable": False, "dst_role": "comprador"}, headers=h)
    assert r.json()["rol_destino"] == "comprador"


def test_diagrama_completo_incluye_notacion(client, h, modelo):
    # /full responde con los nombres de columna en español (como /classes).
    full = client.get(f"/diagrams/{modelo['did']}/full", headers=h).json()
    kinds = {c["nombre"]: c["tipo_clase"] for c in full["clases"]}
    assert kinds["Pagable"] == "interface"
    rel = next(r for r in full["relaciones"] if r["tipo"] == "ASSOCIATION")
    assert rel["rol_origen"] == "pedidos" and rel["navegable_destino"] is True


# ---------------------------------------------------------------- XMI
def test_xmi_exporta_la_notacion(client, h, modelo):
    xmi = client.get(f"/diagrams/{modelo['did']}/export-xmi", headers=h)
    assert xmi.status_code == 200
    text = xmi.text
    assert 'xmi:type="uml:Interface"' in text
    assert 'xmi:type="uml:Enumeration"' in text and "ownedLiteral" in text
    assert 'isAbstract="true"' in text
    assert "interfaceRealization" in text
    assert "navigableOwnedEnd" in text
    assert 'visibility="protected"' in text
    assert 'isStatic="true"' in text and 'isDerived="true"' in text
    assert 'direction="in"' in text
    assert 'name="comprador"' in text


def test_xmi_ida_y_vuelta_conserva_la_notacion(client, h, modelo):
    xmi = client.get(f"/diagrams/{modelo['did']}/export-xmi", headers=h).content
    dst = _diagram(client, h, "UML 2.5 - reimportado")
    r = client.post(f"/diagrams/{dst}/import-xmi",
                    files={"file": ("modelo.xmi", io.BytesIO(xmi), "application/xml")}, headers=h)
    assert r.status_code == 200, r.text

    clases = {c["nombre"]: c for c in client.get(f"/diagrams/{dst}/classes", headers=h).json()}
    assert {n: c["tipo_clase"] for n, c in clases.items()} == {
        "Pagable": "interface", "Pedido": "abstract", "Cliente": "class", "EstadoPedido": "enumeration",
    }
    assert sorted(a["nombre"] for a in clases["EstadoPedido"]["atributos"]) == ["PAGADO", "PENDIENTE"]

    attrs = {a["nombre"]: a for a in clases["Pedido"]["atributos"]}
    assert attrs["total"]["es_derivado"] is True
    assert attrs["contador"]["es_estatico"] is True and attrs["contador"]["visibilidad"] == "+"

    metodos = {m["nombre"]: m for m in clases["Pedido"]["metodos"]}
    assert metodos["calcularTotal"]["es_abstracto"] is True
    assert metodos["calcularTotal"]["parametros"] == "descuento: double, cupon: string"
    crear = {m["nombre"]: m for m in clases["Cliente"]["metodos"]}["crear"]
    assert crear["es_estatico"] is True and crear["parametros"] == "nombre: string"

    rels = client.get(f"/diagrams/{dst}/relations", headers=h).json()
    tipos = sorted(r["tipo"] for r in rels)
    assert tipos == ["ASSOCIATION", "REALIZATION"]
    asoc = next(r for r in rels if r["tipo"] == "ASSOCIATION")
    assert asoc["rol_origen"] == "pedidos" and asoc["rol_destino"] == "comprador"
    assert asoc["navegable_destino"] is True and asoc["navegable_origen"] is False


# ---------------------------------------------------------------- generador
def test_generador_ignora_interfaces_enumeraciones_y_realizaciones(client, h, modelo):
    r = client.post(f"/diagrams/{modelo['did']}/export-download", headers=h)
    assert r.status_code == 200, r.text[:300]
    z = zipfile.ZipFile(io.BytesIO(r.content))
    java = [n.rsplit("/", 1)[-1] for n in z.namelist() if n.endswith(".java")]
    assert "PedidoRepository.java" in java and "ClienteRepository.java" in java
    assert not any(n.startswith(("Pagable", "EstadoPedido")) for n in java)

    pedido = next(n for n in z.namelist() if n.endswith("/Pedido.java"))
    src = z.read(pedido).decode()
    # derivado y estático no son columnas
    assert " total;" not in src and " contador;" not in src
