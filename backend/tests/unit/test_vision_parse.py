"""
Import desde foto: cómo se interpreta lo que devuelve Gemini (sin llamarlo:
se reemplaza el cliente por un doble que responde un JSON fijo).

- Diagrama de base de datos: tipos SQL -> tipos del editor.
- Notación UML 2.5: tipo de clase, visibilidad, estático, derivado,
  multiplicidad, valor inicial, métodos con parámetros, realización, roles.
- Valores inválidos que Gemini a veces inventa se descartan en vez de
  romper la creación del diagrama.
"""
import json
from types import SimpleNamespace

from app.services import diagram_vision

RESPUESTA = {
    "source": "er",
    "classes": [
        {"name": "pedido", "kind": "tabla", "attributes": [
            {"name": "id", "type": "BIGINT", "required": True},
            {"name": "total", "type": "NUMERIC(10,2)"},
            {"name": "alta", "type": "TIMESTAMP"},
            {"name": "nota", "type": "VARCHAR(200)", "visibility": "publico", "multiplicity": "1,2"},
            {"name": "estado", "type": "EstadoPedido"},
        ]},
        {"name": "Pagable", "kind": "interface", "methods": [
            {"name": "pagar()", "params": "(monto: double)", "return_type": "Boolean", "is_abstract": True},
        ]},
        {"name": "Factura", "kind": "abstract", "attributes": [
            {"name": "contador", "type": "int", "visibility": "+", "is_static": True},
            {"name": "saldo", "type": "double", "is_derived": True, "multiplicity": "0..1", "default_value": " 0 "},
        ], "methods": [{"name": "crear", "params": "", "is_static": True}]},
    ],
    "relations": [
        {"from_class": "Factura", "to_class": "Pagable", "type": "REALIZATION"},
        {"from_class": "pedido", "to_class": "Factura", "type": "association",
         "src_multiplicity": "0..*", "dst_multiplicity": "uno", "src_role": " pedidos ", "dst_navigable": True},
    ],
}


def _detect(monkeypatch, payload):
    class FakeModels:
        def generate_content(self, **kw):
            return SimpleNamespace(text=json.dumps(payload))

    class FakeClient:
        def __init__(self, **kw):
            self.models = FakeModels()

    monkeypatch.setattr(diagram_vision.settings, "GEMINI_API_KEY", "x")
    monkeypatch.setattr(diagram_vision.genai, "Client", FakeClient)
    return diagram_vision.detect_from_image(b"img", "image/png")


def test_interpreta_base_de_datos_y_notacion_uml25(monkeypatch):
    r = _detect(monkeypatch, RESPUESTA)
    assert r.source == "er"
    c = {k.name: k for k in r.classes}

    pedido = {a.name: a for a in c["pedido"].attributes}
    assert c["pedido"].kind == "class"  # "tabla" no es un tipo válido
    assert pedido["id"].type == "long" and pedido["id"].required
    assert pedido["total"].type == "decimal"
    assert pedido["alta"].type == "datetime"
    assert pedido["nota"].type == "string"
    assert pedido["nota"].visibility == "-"       # visibilidad inválida -> la de siempre
    assert pedido["nota"].multiplicity is None    # "1,2" no es una multiplicidad
    assert pedido["estado"].type == "EstadoPedido"  # tipo propio: se conserva

    pagar = c["Pagable"].methods[0]
    assert c["Pagable"].kind == "interface"
    assert (pagar.name, pagar.params, pagar.return_type) == ("pagar", "monto: double", "boolean")
    assert pagar.is_abstract and pagar.visibility == "+"

    f = {a.name: a for a in c["Factura"].attributes}
    assert c["Factura"].kind == "abstract"
    assert f["contador"].is_static and f["contador"].visibility == "+"
    assert f["saldo"].is_derived and f["saldo"].multiplicity == "0..1" and f["saldo"].default_value == "0"
    assert c["Factura"].methods[0].return_type == "void" and c["Factura"].methods[0].is_static

    real, asoc = r.relations
    assert real.type == "REALIZATION"
    assert asoc.type == "ASSOCIATION"
    assert (asoc.src_multiplicity, asoc.dst_multiplicity) == ("0..*", None)
    assert asoc.src_role == "pedidos" and asoc.dst_navigable and not asoc.src_navigable


def test_fuente_desconocida_es_uml(monkeypatch):
    r = _detect(monkeypatch, {"source": "otra", "classes": [{"name": "A"}], "relations": []})
    assert r.source == "uml" and r.classes[0].kind == "class"
