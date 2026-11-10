"""
CU-06: compatibilidad con Enterprise Architect, con archivos REALES de EA
17.2 (no XMI escrito a mano):

- fixtures/xmi/ea_ejemplo_completo.xmi: el XMI del editor importado en EA y
  vuelto a exportar por EA (XMI 2.1). Importarlo tiene que reconstruir el
  diagrama original del editor (docs/xmi/ejemplo-completo.xmi).
- fixtures/xmi/ea_tipos.xmi: una clase creada en EA con atributos Date,
  Double, Long, BigDecimal... EA no los escribe en la parte UML (sin <type>,
  y Long como UnlimitedNatural): estan en su xmi:Extension.

Y la exportacion del editor con lo que EA necesita (ver services/xmi.py).
"""
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace as NS

from app.models.uml import RelType
from app.services.xmi import build_xmi, parse_xmi

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "xmi"
XMI = "{http://schema.omg.org/spec/XMI/2.1}"


def _parse(name):
    return parse_xmi((FIX / name).read_bytes())


def test_ea_tipos_salen_de_la_extension_de_ea():
    r = _parse("ea_tipos.xmi")
    tipos = {a.name: a.type for c in r.classes for a in c.attributes}
    assert tipos["aDate"] == "date"
    assert tipos["aDouble"] == "double"
    assert tipos["aLong"] == "long"  # en la parte UML EA lo escribe como UnlimitedNatural
    assert tipos["aBigDecimal"] == "BigDecimal"
    assert tipos["aLocalDateTime"] == "LocalDateTime"
    assert tipos["aInteger"] == "int" and tipos["aString"] == "string"


def test_ea_ejemplo_completo_reconstruye_el_diagrama_del_editor():
    r = _parse("ea_ejemplo_completo.xmi")
    assert not r.warnings
    assert sorted(c.name for c in r.classes) == sorted([
        "Persona", "Cliente", "Empleado", "Pedido", "DetallePedido",
        "Producto", "Categoria", "Proveedor", "Direccion", "Factura",
    ])
    tipos = {(c.name, a.name): a.type for c in r.classes for a in c.attributes}
    assert tipos[("Pedido", "fecha")] == "date"
    assert tipos[("Pedido", "total")] == "BigDecimal"
    assert tipos[("Empleado", "sueldo")] == "double"
    assert tipos[("Producto", "codigo")] == "long"

    rels = {(x.from_name, x.to_name, x.type): (x.src_mult_min, x.src_mult_max, x.dst_mult_min, x.dst_mult_max)
            for x in r.relations}
    # Direccion del editor (no la invertida) y multiplicidad en la clase correcta.
    assert rels[("Cliente", "Pedido", "ASSOCIATION")] == (1, 1, 0, None)
    assert rels[("Empleado", "Pedido", "ASSOCIATION")] == (0, None, 0, None)
    # Recursiva: los dos extremos son Categoria, desempata la multiplicidad.
    assert rels[("Categoria", "Categoria", "ASSOCIATION")] == (0, None, 0, 1)
    # Parte -> todo, como en el editor (rombo en el destino).
    assert rels[("DetallePedido", "Pedido", "COMPOSITION")] == (1, None, 1, 1)
    assert ("Producto", "Proveedor", "AGGREGATION") in rels
    assert ("Cliente", "Persona", "INHERITANCE") in rels
    assert ("Pedido", "Factura", "DEPENDENCY") in rels


def _diagrama():
    """Objeto con la forma minima que usa build_xmi (como los modelos ORM)."""
    detalle = NS(id="d", nombre="DetallePedido", metodos=[], outgoing_relations=[],
                 atributos=[NS(id="a1", nombre="cantidad", tipo="Integer", requerido=True)])
    pedido = NS(id="p", nombre="Pedido", metodos=[], outgoing_relations=[],
                atributos=[NS(id="a2", nombre="fecha", tipo="Date", requerido=True),
                           NS(id="a3", nombre="total", tipo="BigDecimal", requerido=False)])
    comp = NS(id="r1", tipo=RelType.COMPOSITION, origen_id="d", destino_id="p", etiqueta=None,
              mult_origen_min=1, mult_origen_max=None, mult_destino_min=1, mult_destino_max=1)
    return NS(title="t", classes=[detalle, pedido], relations=[comp])


def test_export_compatible_con_ea():
    root = ET.fromstring(build_xmi(_diagrama()))
    by_id = {e.get(f"{XMI}id"): e for e in root.iter() if e.get(f"{XMI}id")}

    # Tipos no primitivos: uml:DataType con su nombre, referenciado con el
    # atributo `type` (con un hijo <type xmi:idref> EA lo dejaba sin tipo).
    fecha = next(e for e in root.iter("ownedAttribute") if e.get("name") == "fecha")
    total = next(e for e in root.iter("ownedAttribute") if e.get("name") == "total")
    assert by_id[fecha.get("type")].get("name") == "Date"
    assert by_id[total.get("type")].get("name") == "BigDecimal"  # antes se exportaba como String

    assoc = next(e for e in root.iter("packagedElement") if e.get(f"{XMI}type") == "uml:Association")
    ends = [e for e in assoc if e.tag == "ownedEnd"]
    # Marca de composicion en el extremo de la PARTE (DetallePedido): el rombo
    # queda en el todo. Antes iba en el destino y EA lo dibujaba al reves.
    assert ends[0].get("type") == "C_d" and ends[0].get("aggregation") == "composite"
    assert ends[1].get("aggregation") == "none"
    # memberEnd destino primero: EA lo toma como destino del conector.
    assert [m.get(f"{XMI}idref") for m in assoc if m.tag == "memberEnd"] == ["E2_r1", "E1_r1"]

    # Y el propio importador lo lee igual que se exporto.
    r = parse_xmi(build_xmi(_diagrama()))
    rel = r.relations[0]
    assert (rel.from_name, rel.to_name, rel.type) == ("DetallePedido", "Pedido", "COMPOSITION")
    assert {a.name: a.type for c in r.classes for a in c.attributes}["total"] == "BigDecimal"
