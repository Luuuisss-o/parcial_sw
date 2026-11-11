"""
Import de XMI más allá del diagrama de clases básico:

- Un modelo de datos de Enterprise Architect (tablas «table», columnas
  «column», PK/FK como operaciones «PK»/«FK»): las restricciones no entran
  como métodos, la PK queda obligatoria, la columna FK se reemplaza por la
  relación y los tipos SQL se traducen.
- La notación UML 2.5 tal como la escriben otras herramientas: realización
  como elemento suelto (uml:Realization), interfaz, enumeración con
  literales, parámetros de operaciones.
"""
from pathlib import Path

from exporters.generators.type_mapping import map_type
from app.services.xmi import parse_xmi

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "xmi"


def test_modelo_de_datos_de_ea():
    r = parse_xmi((FIX / "ea_modelo_datos.xmi").read_bytes())
    clases = {c.name: c for c in r.classes}
    assert set(clases) == {"cliente", "pedido"}

    # PK / FK / índices no son métodos del modelo de clases
    assert clases["cliente"].methods == [] and clases["pedido"].methods == []

    cli = {a.name: a for a in clases["cliente"].attributes}
    ped = {a.name: a for a in clases["pedido"].attributes}
    # La columna FK la representa la relación (si no, el backend generado la duplica)
    assert "cliente_id" not in ped
    # La PK es obligatoria
    assert cli["id"].required and ped["id"].required
    # Tipos SQL -> tipos del editor -> tipo Java correcto
    assert cli["nombre"].type == "string" and cli["fecha_alta"].type == "date"
    assert ped["id"].type == "long" and map_type(ped["id"].type) == "Long"
    assert ped["total"].type == "decimal" and map_type(ped["total"].type) == "java.math.BigDecimal"
    assert ped["fecha"].type == "datetime"

    assert len(r.relations) == 1
    rel = r.relations[0]
    assert (rel.from_name, rel.to_name, rel.type) == ("pedido", "cliente", "ASSOCIATION")
    assert (rel.src_mult_min, rel.src_mult_max) == (0, None)   # 0..*
    assert (rel.dst_mult_min, rel.dst_mult_max) == (1, 1)


_UML25 = b"""<?xml version="1.0" encoding="UTF-8"?>
<xmi:XMI xmi:version="2.1" xmlns:uml="http://schema.omg.org/spec/UML/2.1" xmlns:xmi="http://schema.omg.org/spec/XMI/2.1">
  <uml:Model xmi:type="uml:Model" xmi:id="m" name="m">
    <packagedElement xmi:type="uml:Interface" xmi:id="I1" name="Pagable">
      <ownedOperation xmi:id="O1" name="pagar" visibility="public" isAbstract="true">
        <ownedParameter xmi:id="P1" name="monto" direction="in">
          <type xmi:type="uml:PrimitiveType" href="http://schema.omg.org/spec/UML/2.1/uml.xml#Real"/>
        </ownedParameter>
        <ownedParameter xmi:id="P2" name="return" direction="return">
          <type xmi:type="uml:PrimitiveType" href="http://schema.omg.org/spec/UML/2.1/uml.xml#Boolean"/>
        </ownedParameter>
      </ownedOperation>
    </packagedElement>
    <packagedElement xmi:type="uml:Enumeration" xmi:id="E1" name="Estado">
      <ownedLiteral xmi:type="uml:EnumerationLiteral" xmi:id="L1" name="ABIERTO"/>
      <ownedLiteral xmi:type="uml:EnumerationLiteral" xmi:id="L2" name="CERRADO"/>
    </packagedElement>
    <packagedElement xmi:type="uml:Class" xmi:id="C1" name="Factura" isAbstract="true">
      <ownedAttribute xmi:type="uml:Property" xmi:id="A1" name="contador" visibility="protected" isStatic="true"/>
    </packagedElement>
    <packagedElement xmi:type="uml:Realization" xmi:id="R1" client="C1" supplier="I1"/>
  </uml:Model>
</xmi:XMI>
"""


def test_notacion_uml25_de_otras_herramientas():
    r = parse_xmi(_UML25)
    clases = {c.name: c for c in r.classes}
    assert clases["Pagable"].kind == "interface"
    assert clases["Estado"].kind == "enumeration"
    assert [a.name for a in clases["Estado"].attributes] == ["ABIERTO", "CERRADO"]
    assert clases["Factura"].kind == "abstract"
    contador = clases["Factura"].attributes[0]
    assert contador.visibility == "#" and contador.is_static

    pagar = clases["Pagable"].methods[0]
    assert pagar.params == "monto: float" and pagar.return_type == "boolean" and pagar.is_abstract

    assert [(x.from_name, x.to_name, x.type) for x in r.relations] == [("Factura", "Pagable", "REALIZATION")]
