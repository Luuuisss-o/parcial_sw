# app/services/xmi.py
"""
Interoperabilidad XMI con Enterprise Architect (requisito de la catedra:
"la herramienta se deberia poder integrar con el Architect sin mayor
problema, ya sea importando o exportando... generalmente se utiliza un
mecanismo basado en XMI, que es una especializacion de XML").

Exportamos y parseamos un subconjunto de UML 2.x XMI 2.1 (el mismo dialecto
que entiende EA de forma nativa): paquete -> uml:Class con ownedAttribute,
generalization para herencia, y uml:Association (con ownedEnd, agregacion y
multiplicidad) para el resto de las relaciones.

Import defensivo a proposito: un archivo XMI exportado por otra herramienta
(o por versiones distintas de EA) varia bastante en como referencia tipos y
extremos de asociacion. El objetivo del profesor es "no partir de cero", asi
que preferimos importar clases/atributos/relaciones de forma best-effort en
vez de rechazar el archivo entero por un detalle que no podemos resolver.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

from app.models.uml import RelType

XMI_NS = "http://schema.omg.org/spec/XMI/2.1"
UML_NS = "http://schema.omg.org/spec/UML/2.1"
NS = {"xmi": XMI_NS, "uml": UML_NS}

ET.register_namespace("xmi", XMI_NS)
ET.register_namespace("uml", UML_NS)

# UML primitive types estandar (los entiende cualquier herramienta UML2 sin
# resolver nada mas: se referencian por href, no hace falta definirlos).
_PRIMITIVE_HREF = "http://schema.omg.org/spec/UML/2.1/uml.xml#{name}"
_TO_UML_PRIMITIVE = {
    "int": "Integer", "integer": "Integer",
    "float": "Real",
    "boolean": "Boolean", "bool": "Boolean",
    "string": "String", "text": "String", "uuid": "String", "email": "String",
}
# Cualquier otro tipo (Date, Double, BigDecimal, LocalDateTime, Long...) se
# declara como uml:DataType propio con su nombre, dentro del mismo archivo.
# Antes double/decimal/long se mapeaban a los primitivos Real/Integer y
# volvian como float/int (el backend generado perdia precision), y los
# tipos desconocidos se exportaban como String. Nombres canonicos para los
# alias en minuscula; el resto conserva el nombre tal cual lo escribio el
# usuario.
_LOCAL_DATATYPES = {
    "date": "Date", "datetime": "DateTime",
    "double": "Double", "decimal": "Decimal", "long": "Long",
}


def _datatype_ref(tipo: str, used: dict[str, str]) -> str:
    """Registra el DataType de `tipo` y devuelve su xmi:id."""
    key = tipo.strip().lower()
    used.setdefault(key, _LOCAL_DATATYPES.get(key, tipo.strip()))
    return "DT_" + "".join(ch if ch.isalnum() else "_" for ch in key)

# Vuelta: nombre de primitivo/datatype UML (en minuscula) -> tipo interno.
# Escrito explicito, no derivado de _TO_UML_PRIMITIVE: ese dict tiene varias
# claves internas apuntando al mismo primitivo UML (int/integer/long ->
# Integer), asi que invertirlo automaticamente pierde informacion sobre cual
# es el nombre "canonico" a usar de vuelta.
_FROM_UML_PRIMITIVE = {"integer": "int", "real": "float", "boolean": "boolean", "string": "string"}
_FROM_LOCAL_DATATYPE = {
    "date": "date", "datetime": "datetime",
    "double": "double", "decimal": "decimal", "long": "long",
}
# Tipos SQL de un modelo de datos de Enterprise Architect (tablas «table» con
# columnas «column»): sin esto BIGINT, NUMERIC o VARCHAR llegaban tal cual y
# el generador los convertía todos en String.
_FROM_SQL_TYPE = {
    "varchar": "string", "varchar2": "string", "nvarchar": "string", "char": "string", "nchar": "string",
    "character varying": "string", "text": "text", "clob": "text", "longtext": "text", "mediumtext": "text",
    "int": "int", "integer": "int", "smallint": "int", "tinyint": "int", "serial": "int", "mediumint": "int",
    "bigint": "long", "bigserial": "long", "number": "decimal", "numeric": "decimal", "money": "decimal",
    "real": "float", "double precision": "double", "bit": "boolean", "bool": "boolean",
    "timestamp": "datetime", "timestamptz": "datetime", "smalldatetime": "datetime", "datetime2": "datetime",
    "uuid": "uuid", "uniqueidentifier": "uuid", "guid": "uuid",
}

# Restricciones de base de datos que EA modela como OPERACIONES de la tabla
# («PK», «FK», «unique», «index»...): no son métodos del modelo de clases.
_DB_CONSTRAINT_STEREOTYPES = {"pk", "fk", "unique", "index", "check", "trigger"}
_DB_CONSTRAINT_PREFIXES = ("PK_", "FK_", "IX_", "IDX_", "UQ_", "UK_", "CK_", "TRG_")

_AGGREGATION_BY_TYPE = {
    RelType.COMPOSITION: "composite",
    RelType.AGGREGATION: "shared",
    RelType.ASSOCIATION: "none",
}
_TYPE_BY_AGGREGATION = {v: k for k, v in _AGGREGATION_BY_TYPE.items()}


def _mult(value: int | None) -> str:
    return "*" if value is None else str(value)


# Notación UML 2.5: visibilidad, tipos de clase, multiplicidad de atributos.
_VISIBILITY_TO_XMI = {"+": "public", "-": "private", "#": "protected", "~": "package"}
_VISIBILITY_FROM_XMI = {v: k for k, v in _VISIBILITY_TO_XMI.items()}
_KIND_TO_XMI = {"interface": "uml:Interface", "enumeration": "uml:Enumeration"}


def _split_mult(text: str | None) -> tuple[str, str] | None:
    """"0..*" -> ("0", "*"); "1" -> ("1", "1"); "*" -> ("0", "*")."""
    if not text:
        return None
    if ".." in text:
        lo, hi = text.split("..", 1)
        return lo, hi
    return ("0", "*") if text == "*" else (text, text)


def _parse_params(text: str | None) -> list[tuple[str, str]]:
    """"id: Long, nombre: String" -> [("id", "Long"), ("nombre", "String")]."""
    out = []
    for chunk in (text or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        name, _, typ = chunk.partition(":")
        out.append((name.strip() or "arg", typ.strip() or "string"))
    return out


def _type_child(parent: ET.Element, tipo: str, used: dict[str, str]) -> None:
    """Asigna el tipo a un Property/Parameter: primitivo UML por href o
    DataType propio por el atributo `type` (como lo entiende EA)."""
    tipo = (tipo or "string").strip()
    if tipo.lower() in _TO_UML_PRIMITIVE:
        ET.SubElement(parent, "type", {
            f"{{{XMI_NS}}}type": "uml:PrimitiveType",
            "href": _PRIMITIVE_HREF.format(name=_TO_UML_PRIMITIVE[tipo.lower()]),
        })
    else:
        parent.set("type", _datatype_ref(tipo, used))


# =====================================================================
# Diagrama de Enterprise Architect (posiciones de las clases)
# =====================================================================
# Sin esto, EA importa el modelo pero no un diagrama: las clases quedan en
# el Project Browser y, al arrastrarlas a un diagrama (o al crearlo EA),
# todas aparecen apiladas en el mismo punto. EA lee el diagrama con la
# geometria de cada elemento de su extension del XMI
# (xmi:Extension/diagrams/diagram/elements/element@geometry).

_EA_PX = 16          # px por celda de la grilla del editor
_EA_MARGIN = 40      # margen del diagrama, px
_EA_GAP = 40         # separacion minima entre clases, px
_EA_LINE = 15        # alto de una linea de atributo/operacion en EA, px
_EA_CHAR = 7         # ancho aproximado de un caracter en EA, px


def _ea_guid(prefix: str, value) -> str:
    """Id con forma de GUID de EA ("EAID_XXXXXXXX_XXXX_..."): EA lo conserva
    tal cual al importar, asi que importar dos veces el mismo diagrama no
    duplica su diagrama."""
    return f"{prefix}_" + str(value).upper().replace("-", "_")


def _ea_box(c) -> tuple[int, int]:
    """Ancho y alto (px) que va a ocupar la clase en EA: el tamaño que tiene
    en el editor, o el que necesita su texto si es mas grande."""
    lines = [c.nombre] + [f"- {a.nombre}: {a.tipo}" for a in c.atributos] \
        + [f"+ {m.nombre}({getattr(m, 'parametros', '') or ''}): {m.tipo_retorno}" for m in c.metodos]
    width = max((getattr(c, "w_grid", None) or 12) * _EA_PX, max(len(t) for t in lines) * _EA_CHAR + 30)
    needed = 40 + _EA_LINE * (len(c.atributos) + len(c.metodos)) + 16
    height = max((getattr(c, "h_grid", None) or 6) * _EA_PX, needed)
    return int(width), int(height)


def _ea_layout(classes) -> dict:
    """{class_id: (left, top, right, bottom)} sin superposiciones. Parte de
    la posicion de cada clase en el editor; las que chocan bajan debajo de la
    que las tapa, en su misma columna (mismo criterio que el reacomodo de la
    web, frontend/src/components/canvas/utils/layout.js)."""
    rects = []
    for c in classes:
        w, h = _ea_box(c)
        rects.append({"id": c.id, "x": _EA_MARGIN + (getattr(c, "x_grid", None) or 0) * _EA_PX,
                      "y": _EA_MARGIN + (getattr(c, "y_grid", None) or 0) * _EA_PX, "w": w, "h": h})
    rects.sort(key=lambda r: (r["y"], r["x"]))

    def hit(a, b):
        return (a["x"] < b["x"] + b["w"] + _EA_GAP and b["x"] < a["x"] + a["w"] + _EA_GAP
                and a["y"] < b["y"] + b["h"] + _EA_GAP and b["y"] < a["y"] + a["h"] + _EA_GAP)

    placed = []
    for r in rects:
        while True:
            hits = [p for p in placed if hit(r, p)]
            if not hits:
                break
            r["y"] = max(p["y"] + p["h"] + _EA_GAP for p in hits)
        placed.append(r)
    return {r["id"]: (r["x"], r["y"], r["x"] + r["w"], r["y"] + r["h"]) for r in placed}


def _add_ea_diagram(root: ET.Element, diagram, model_id: str, class_ids: dict) -> None:
    ext = ET.SubElement(root, f"{{{XMI_NS}}}Extension", {
        "extender": "Enterprise Architect", "extenderID": "6.5",
    })
    diagrams = ET.SubElement(ext, "diagrams")
    dg = ET.SubElement(diagrams, "diagram", {f"{{{XMI_NS}}}id": _ea_guid("EAID", getattr(diagram, "id", "diagrama"))})
    ET.SubElement(dg, "model", {"package": model_id, "localID": "1", "owner": model_id})
    ET.SubElement(dg, "properties", {"name": diagram.title or "Diagrama de clases", "type": "Logical"})
    ET.SubElement(dg, "style1", {"value": "ShowPrivate=1;ShowProtected=1;ShowPublic=1;"
                                          "ConnectorNotation=UML 2.1;ExplicitNavigability=1;"
                                          "OpParams=3;ShowOpRetType=1;"})
    elements = ET.SubElement(dg, "elements")

    layout = _ea_layout(diagram.classes)
    for seq, c in enumerate(diagram.classes, start=1):
        left, top, right, bottom = layout[c.id]
        ET.SubElement(elements, "element", {
            "geometry": f"Left={left};Top={top};Right={right};Bottom={bottom};",
            "subject": class_ids[c.id],
            "seqno": str(seq),
            "style": "DUID=" + str(c.id).replace("-", "")[:8].upper() + ";",
        })
    # Conectores del diagrama (EA dibuja la linea entre los elementos).
    prefix = {RelType.INHERITANCE: "G", RelType.REALIZATION: "R", RelType.DEPENDENCY: "D"}
    for r in diagram.relations:
        if r.origen_id not in layout or r.destino_id not in layout:
            continue
        ET.SubElement(elements, "element", {
            "geometry": "SX=0;SY=0;EX=0;EY=0;EDGE=0;",
            "subject": f"{prefix.get(r.tipo, 'AS')}_{r.id}",
            "style": "Mode=3;Hidden=0;",
        })


# =====================================================================
# Export: diagrama -> XMI
# =====================================================================
def build_xmi(diagram) -> bytes:
    root = ET.Element(f"{{{XMI_NS}}}XMI", {f"{{{XMI_NS}}}version": "2.1"})
    # Id propio por diagrama (no un "model_1" fijo): EA convierte el modelo
    # en un paquete, y el diagrama de EA lo referencia por este id.
    model_id = _ea_guid("EAPK", getattr(diagram, "id", "modelo"))
    model = ET.SubElement(root, f"{{{UML_NS}}}Model", {
        f"{{{XMI_NS}}}type": "uml:Model",
        f"{{{XMI_NS}}}id": model_id,
        "name": diagram.title or "diagram",
    })

    class_ids = {c.id: f"C_{c.id}" for c in diagram.classes}
    used_datatypes: dict[str, str] = {}  # clave en minuscula -> nombre del DataType

    for c in diagram.classes:
        kind = getattr(c, "tipo_clase", None) or "class"
        el = ET.SubElement(model, "packagedElement", {
            f"{{{XMI_NS}}}type": _KIND_TO_XMI.get(kind, "uml:Class"),
            f"{{{XMI_NS}}}id": class_ids[c.id],
            "name": c.nombre,
        })
        if kind in ("abstract", "interface"):
            el.set("isAbstract", "true")

        if kind == "enumeration":
            # En una enumeración los atributos son sus literales.
            for a in c.atributos:
                ET.SubElement(el, "ownedLiteral", {
                    f"{{{XMI_NS}}}type": "uml:EnumerationLiteral",
                    f"{{{XMI_NS}}}id": f"L_{a.id}",
                    "name": a.nombre,
                })

        for a in ([] if kind == "enumeration" else c.atributos):
            attr_el = ET.SubElement(el, "ownedAttribute", {
                f"{{{XMI_NS}}}type": "uml:Property",
                f"{{{XMI_NS}}}id": f"A_{a.id}",
                "name": a.nombre,
                "visibility": _VISIBILITY_TO_XMI.get(getattr(a, "visibilidad", None) or "-", "private"),
            })
            if a.requerido:
                attr_el.set("isNullable", "false")
            if getattr(a, "es_estatico", False):
                attr_el.set("isStatic", "true")
            if getattr(a, "es_derivado", False):
                attr_el.set("isDerived", "true")

            tipo = (a.tipo or "string").strip()
            if tipo.lower() in _TO_UML_PRIMITIVE:
                ET.SubElement(attr_el, "type", {
                    f"{{{XMI_NS}}}type": "uml:PrimitiveType",
                    "href": _PRIMITIVE_HREF.format(name=_TO_UML_PRIMITIVE[tipo.lower()]),
                })
            else:
                # Referencia como atributo `type` (no como hijo <type
                # xmi:idref>): Enterprise Architect solo vincula el atributo
                # al DataType de esta forma; con el hijo lo importaba sin tipo
                # (verificado con EA 17.2).
                attr_el.set("type", _datatype_ref(tipo, used_datatypes))

            mult = _split_mult(getattr(a, "multiplicidad", None))
            if mult:
                ET.SubElement(attr_el, "lowerValue", {f"{{{XMI_NS}}}type": "uml:LiteralInteger", "value": mult[0]})
                ET.SubElement(attr_el, "upperValue", {f"{{{XMI_NS}}}type": "uml:LiteralUnlimitedNatural", "value": mult[1]})
            default = getattr(a, "valor_inicial", None)
            if default:
                ET.SubElement(attr_el, "defaultValue", {
                    f"{{{XMI_NS}}}type": "uml:OpaqueExpression",
                    f"{{{XMI_NS}}}id": f"AV_{a.id}",
                    "body": default,
                })

        for m in c.metodos:
            op_el = ET.SubElement(el, "ownedOperation", {
                f"{{{XMI_NS}}}id": f"M_{m.id}",
                "name": m.nombre,
                "visibility": _VISIBILITY_TO_XMI.get(getattr(m, "visibilidad", None) or "+", "public"),
            })
            if getattr(m, "es_estatico", False):
                op_el.set("isStatic", "true")
            if getattr(m, "es_abstracto", False) or kind == "interface":
                op_el.set("isAbstract", "true")
            for i, (pname, ptype) in enumerate(_parse_params(getattr(m, "parametros", ""))):
                p_el = ET.SubElement(op_el, "ownedParameter", {
                    f"{{{XMI_NS}}}id": f"MP_{m.id}_{i}",
                    "name": pname,
                    "direction": "in",
                })
                _type_child(p_el, ptype, used_datatypes)
            ret = (m.tipo_retorno or "void").strip().lower()
            if ret == "void":
                ET.SubElement(op_el, "ownedParameter", {
                    f"{{{XMI_NS}}}id": f"MR_{m.id}",
                    "name": "return",
                    "direction": "return",
                    "type": "EAnone_void",
                })
            else:
                param_el = ET.SubElement(op_el, "ownedParameter", {
                    f"{{{XMI_NS}}}id": f"MR_{m.id}",
                    "name": "return",
                    "direction": "return",
                })
                if ret in _TO_UML_PRIMITIVE:
                    ET.SubElement(param_el, "type", {
                        f"{{{XMI_NS}}}type": "uml:PrimitiveType",
                        "href": _PRIMITIVE_HREF.format(name=_TO_UML_PRIMITIVE[ret]),
                    })
                else:
                    # Igual que los atributos (antes date/double -> String).
                    param_el.set("type", _datatype_ref(m.tipo_retorno, used_datatypes))

        # Herencia: generalization vive DENTRO del elemento hijo (origen).
        # Realización (UML 2.5): interfaceRealization, también en el que
        # implementa, con la interfaz como contrato.
        for r in c.outgoing_relations:
            if r.tipo == RelType.INHERITANCE:
                ET.SubElement(el, "generalization", {
                    f"{{{XMI_NS}}}id": f"G_{r.id}",
                    "general": class_ids[r.destino_id],
                })
            elif r.tipo == RelType.REALIZATION:
                ET.SubElement(el, "interfaceRealization", {
                    f"{{{XMI_NS}}}type": "uml:InterfaceRealization",
                    f"{{{XMI_NS}}}id": f"R_{r.id}",
                    "client": class_ids[r.origen_id],
                    "supplier": class_ids[r.destino_id],
                    "contract": class_ids[r.destino_id],
                    "implementingClassifier": class_ids[r.origen_id],
                })

    # DataTypes usados, al principio del modelo (definidos antes de usarse).
    for i, (key, name) in enumerate(sorted(used_datatypes.items())):
        dt = ET.Element("packagedElement", {
            f"{{{XMI_NS}}}type": "uml:DataType",
            f"{{{XMI_NS}}}id": "DT_" + "".join(ch if ch.isalnum() else "_" for ch in key),
            "name": name,
        })
        model.insert(i, dt)

    # Resto de las relaciones (asociacion / agregacion / composicion / dependencia).
    for r in diagram.relations:
        if r.tipo in (RelType.INHERITANCE, RelType.REALIZATION):
            continue  # ya se exportaron dentro de la clase

        if r.tipo == RelType.DEPENDENCY:
            ET.SubElement(model, "packagedElement", {
                f"{{{XMI_NS}}}type": "uml:Dependency",
                f"{{{XMI_NS}}}id": f"D_{r.id}",
                "client": class_ids[r.origen_id],
                "supplier": class_ids[r.destino_id],
                **({"name": r.etiqueta} if r.etiqueta else {}),
            })
            continue

        assoc = ET.SubElement(model, "packagedElement", {
            f"{{{XMI_NS}}}type": "uml:Association",
            f"{{{XMI_NS}}}id": f"AS_{r.id}",
            **({"name": r.etiqueta} if r.etiqueta else {}),
        })
        # Orden de memberEnd: destino, origen. Enterprise Architect toma el
        # primer memberEnd como destino del conector; en el orden inverso
        # importaba las asociaciones al reves (Pedido -> Cliente en vez de
        # Cliente -> Pedido). Verificado con EA 17.2. Los ownedEnd siguen en
        # orden origen, destino (es lo que lee parse_xmi).
        ET.SubElement(assoc, "memberEnd", {f"{{{XMI_NS}}}idref": f"E2_{r.id}"})
        ET.SubElement(assoc, "memberEnd", {f"{{{XMI_NS}}}idref": f"E1_{r.id}"})

        # UML: aggregation="shared"/"composite" va en el extremo cuyo tipo es
        # la PARTE, y el rombo se dibuja en el opuesto (el todo). En el editor
        # la parte es el origen y el todo el destino (rombo en el destino).
        # Antes iba en el destino y Enterprise Architect dibujaba el rombo en
        # la clase equivocada (verificado importando en EA 17.2).
        end1 = ET.SubElement(assoc, "ownedEnd", {
            f"{{{XMI_NS}}}type": "uml:Property",
            f"{{{XMI_NS}}}id": f"E1_{r.id}",
            "type": class_ids[r.origen_id],
            "aggregation": _AGGREGATION_BY_TYPE.get(r.tipo, "none"),
        })
        if getattr(r, "rol_origen", None):
            end1.set("name", r.rol_origen)
        ET.SubElement(end1, "lowerValue", {f"{{{XMI_NS}}}type": "uml:LiteralInteger", "value": _mult(r.mult_origen_min)})
        ET.SubElement(end1, "upperValue", {f"{{{XMI_NS}}}type": "uml:LiteralUnlimitedNatural", "value": _mult(r.mult_origen_max)})

        end2 = ET.SubElement(assoc, "ownedEnd", {
            f"{{{XMI_NS}}}type": "uml:Property",
            f"{{{XMI_NS}}}id": f"E2_{r.id}",
            "type": class_ids[r.destino_id],
            "aggregation": "none",
        })
        if getattr(r, "rol_destino", None):
            end2.set("name", r.rol_destino)
        ET.SubElement(end2, "lowerValue", {f"{{{XMI_NS}}}type": "uml:LiteralInteger", "value": _mult(r.mult_destino_min)})
        ET.SubElement(end2, "upperValue", {f"{{{XMI_NS}}}type": "uml:LiteralUnlimitedNatural", "value": _mult(r.mult_destino_max)})

        # UML 2.5: un extremo navegable se lista en navigableOwnedEnd.
        if getattr(r, "navegable_origen", False):
            ET.SubElement(assoc, "navigableOwnedEnd", {f"{{{XMI_NS}}}idref": f"E1_{r.id}"})
        if getattr(r, "navegable_destino", False):
            ET.SubElement(assoc, "navigableOwnedEnd", {f"{{{XMI_NS}}}idref": f"E2_{r.id}"})

    _add_ea_diagram(root, diagram, model_id, class_ids)

    ET.indent(root, space="  ")
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="utf-8")


# =====================================================================
# Import: XMI -> estructura neutra (el router decide como aplicarla a la BD)
# =====================================================================
@dataclass
class ImportedAttribute:
    name: str
    type: str
    required: bool = False
    visibility: str = "-"
    is_static: bool = False
    is_derived: bool = False
    multiplicity: str | None = None
    default_value: str | None = None


@dataclass
class ImportedMethod:
    name: str
    return_type: str = "void"
    visibility: str = "+"
    is_static: bool = False
    is_abstract: bool = False
    params: str = ""


@dataclass
class ImportedClass:
    xmi_id: str
    name: str
    kind: str = "class"
    attributes: list[ImportedAttribute] = field(default_factory=list)
    methods: list[ImportedMethod] = field(default_factory=list)


@dataclass
class ImportedRelation:
    from_name: str
    to_name: str
    type: str
    label: str | None = None
    src_mult_min: int = 1
    src_mult_max: int | None = 1
    dst_mult_min: int = 1
    dst_mult_max: int | None = 1
    es_clase_asociacion: bool = False
    src_role: str | None = None
    dst_role: str | None = None
    src_navigable: bool = False
    dst_navigable: bool = False


@dataclass
class ImportResult:
    classes: list[ImportedClass] = field(default_factory=list)
    relations: list[ImportedRelation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _local(tag: str) -> str:
    """'{ns}Class' -> 'Class' (para no depender de que el prefijo sea exactamente uml:)."""
    return tag.rsplit("}", 1)[-1]


def _xmi_type(el: ET.Element) -> str | None:
    """Valor crudo de xmi:type (ej. 'uml:Class'), sin tocar el prefijo: los
    llamadores comparan contra 'uml:Class', 'uml:Association', etc."""
    for key, val in el.attrib.items():
        if _local(key) == "type" and key.startswith("{" + XMI_NS):
            return val
    return None


def _xmi_id(el: ET.Element) -> str | None:
    for key, val in el.attrib.items():
        if _local(key) == "id" and key.startswith("{" + XMI_NS):
            return val
    return None


def _resolve_type_name(attr_el: ET.Element, by_id: dict[str, ET.Element]) -> str:
    """Intenta sacarle un tipo legible a un ownedAttribute, tolerando los
    varios estilos con los que distintas versiones/exportadores de EA
    referencian el tipo (href a la libreria estandar, idref a un DataType
    definido en el mismo archivo, o un atributo 'type' plano)."""
    type_el = None
    for child in attr_el:
        if _local(child.tag) == "type":
            type_el = child
            break

    raw = None
    if type_el is not None:
        href = type_el.get("href")
        if href:
            raw = href.rsplit("#", 1)[-1]
        else:
            idref = None
            for key, val in type_el.attrib.items():
                if _local(key) == "idref":
                    idref = val
            if idref and idref in by_id:
                raw = by_id[idref].get("name")
            elif idref:
                raw = idref
    if not raw:
        raw = attr_el.get("type")
        if raw and raw in by_id:  # type="DT_..." -> el DataType del archivo
            raw = by_id[raw].get("name")

    if not raw:
        return "string"
    return _normalize_type(raw)


def _normalize_type(raw: str) -> str:
    """Nombre de tipo del XMI -> tipo del editor. Los conocidos se
    normalizan; los demas (BigDecimal, LocalDateTime...) se conservan tal
    cual en vez de perderse como string. Quita los prefijos de EA
    (EAJava_double -> double)."""
    raw = raw.strip()
    for prefix in ("EAJava_", "EAnone_"):
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
    key = raw.lower()
    sql_key = key.split("(", 1)[0].strip()  # VARCHAR(80) -> varchar
    return (_FROM_UML_PRIMITIVE.get(key) or _FROM_LOCAL_DATATYPE.get(key)
            or _FROM_SQL_TYPE.get(sql_key) or raw)


def _resolve_return_type(op_el: ET.Element, by_id: dict[str, ET.Element]) -> str:
    """El tipo de retorno de un ownedOperation viaja en un ownedParameter
    hijo con direction="return" (no en la propia operation), y suele
    referenciar el tipo via el atributo plano 'type' (ej. "EAnone_void"
    para sin retorno) en vez de href/idref como los atributos normales."""
    for param_el in op_el:
        if _local(param_el.tag) != "ownedParameter":
            continue
        if param_el.get("direction") != "return":
            continue
        raw = param_el.get("type")
        if raw and raw in by_id:  # type="DT_..." -> el DataType del archivo
            raw = by_id[raw].get("name")
        if not raw:
            type_el = None
            for child in param_el:
                if _local(child.tag) == "type":
                    type_el = child
                    break
            if type_el is not None:
                href = type_el.get("href")
                idref = type_el.get(f"{{{XMI_NS}}}idref") or type_el.get("xmi:idref")
                if href:
                    raw = href.rsplit("#", 1)[-1]
                elif idref and idref in by_id:
                    raw = by_id[idref].get("name")
        if not raw:
            return "void"
        key = raw.strip().lower()
        if "void" in key or key.endswith("_void"):
            return "void"
        return _FROM_UML_PRIMITIVE.get(key) or _FROM_LOCAL_DATATYPE.get(key) or raw
    return "void"


def parse_xmi(xml_bytes: bytes) -> ImportResult:
    result = ImportResult()
    try:
        tree = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        result.warnings.append(f"El archivo no es XML valido: {e}")
        return result

    by_id: dict[str, ET.Element] = {}
    for el in tree.iter():
        xid = _xmi_id(el)
        if xid:
            by_id[xid] = el

    classes_by_id: dict[str, ImportedClass] = {}
    name_by_id: dict[str, str] = {}

    # Tipo real de cada atributo segun la extension de Enterprise Architect
    # (xmi:Extension/.../attribute/properties@type). EA no pone Date, Double,
    # BigDecimal... en la parte UML (los deja sin <type>, y Long lo convierte
    # en UnlimitedNatural): sin esto llegaban como string.
    ext_attr_types: dict[str, str] = {}
    for el in tree.iter():
        if _local(el.tag) != "attribute":
            continue
        ref = next((v for k, v in el.attrib.items() if _local(k) == "idref"), None)
        props = next((c for c in el if _local(c.tag) == "properties"), None)
        if ref and props is not None and props.get("type"):
            ext_attr_types[ref] = props.get("type")

    # Estereotipo de cada operacion segun la extension de EA
    # (xmi:Extension/.../operation/stereotype@stereotype): «PK», «FK»... en
    # un modelo de datos.
    ext_op_stereotype: dict[str, str] = {}
    for el in tree.iter():
        if _local(el.tag) != "operation":
            continue
        ref = next((v for k, v in el.attrib.items() if _local(k) == "idref"), None)
        st = next((c for c in el if _local(c.tag) == "stereotype"), None)
        if ref and st is not None and st.get("stereotype"):
            ext_op_stereotype[ref] = st.get("stereotype").strip().lower()

    # --- Clases + atributos ---
    # EA representa una clase de asociacion (UML 2.5: la relacion
    # muchos-a-muchos vista como clase propia) con xmi:type="uml:AssociationClass"
    # en vez de "uml:Class" -- verificado contra un archivo real exportado
    # desde EA con dos clases de asociacion genuinas. Sin este chequeo
    # extra, esas clases se descartaban por completo al importar (no solo
    # perdian el estilo de linea punteada: directamente desaparecian del
    # diagrama resultante).
    for el in tree.iter():
        el_type = _xmi_type(el)
        if el_type not in ("uml:Class", "uml:AssociationClass", "uml:Interface", "uml:Enumeration"):
            continue
        xid = _xmi_id(el)
        name = el.get("name")
        if not xid or not name:
            continue
        if el_type == "uml:Interface":
            kind = "interface"
        elif el_type == "uml:Enumeration":
            kind = "enumeration"
        elif el.get("isAbstract") == "true":
            kind = "abstract"
        else:
            kind = "class"
        ic = ImportedClass(xmi_id=xid, name=name, kind=kind)
        # Literales de una enumeración -> atributos de la clase
        for lit_el in el:
            if _local(lit_el.tag) == "ownedLiteral" and lit_el.get("name"):
                ic.attributes.append(ImportedAttribute(name=lit_el.get("name"), type="string", visibility="+"))
        for attr_el in el:
            if _local(attr_el.tag) != "ownedAttribute":
                continue
            if _xmi_type(attr_el) not in (None, "uml:Property"):
                continue
            attr_name = attr_el.get("name")
            if not attr_name:
                continue
            required = attr_el.get("isNullable") == "false" or attr_el.get("required") == "true"
            # Un ownedAttribute con association="..." es el extremo de una
            # asociación (estilo memberEnd), no un atributo de la clase.
            if attr_el.get("association"):
                continue
            lo = hi = None
            default = None
            for child in attr_el:
                tag = _local(child.tag)
                if tag == "lowerValue":
                    lo = child.get("value")
                elif tag == "upperValue":
                    hi = child.get("value")
                elif tag == "defaultValue":
                    default = child.get("body") or child.get("value")
                    if default is None:
                        body_el = next((b for b in child if _local(b.tag) == "body"), None)
                        default = body_el.text if body_el is not None else None
            multiplicity = None
            if lo is not None or hi is not None:
                lo = lo or "1"
                hi = "*" if hi in ("-1", "*") else (hi or "1")
                if not (lo == "1" and hi == "1"):
                    multiplicity = lo if lo == hi else f"{lo}..{hi}"
            ic.attributes.append(ImportedAttribute(
                name=attr_name,
                type=(_normalize_type(ext_attr_types[_xmi_id(attr_el)]) if _xmi_id(attr_el) in ext_attr_types
                      else _resolve_type_name(attr_el, by_id)),
                required=required,
                visibility=_VISIBILITY_FROM_XMI.get(attr_el.get("visibility") or "private", "-"),
                is_static=attr_el.get("isStatic") == "true",
                is_derived=attr_el.get("isDerived") == "true",
                multiplicity=multiplicity,
                default_value=default,
            ))
        pk_columns: set[str] = set()
        fk_columns: set[str] = set()
        for op_el in el:
            if _local(op_el.tag) != "ownedOperation":
                continue
            op_name = op_el.get("name")
            if not op_name:
                continue
            stereo = ext_op_stereotype.get(_xmi_id(op_el) or "", "")
            if stereo in _DB_CONSTRAINT_STEREOTYPES or op_name.upper().startswith(_DB_CONSTRAINT_PREFIXES):
                # Restriccion de base de datos: sus parametros son las columnas.
                cols = {p.get("name") for p in op_el
                        if _local(p.tag) == "ownedParameter" and p.get("direction") != "return" and p.get("name")}
                if stereo == "pk" or op_name.upper().startswith("PK_"):
                    pk_columns |= cols
                elif stereo == "fk" or op_name.upper().startswith("FK_"):
                    fk_columns |= cols
                continue
            params = []
            for p_el in op_el:
                if _local(p_el.tag) != "ownedParameter" or p_el.get("direction") == "return":
                    continue
                params.append(f"{p_el.get('name') or 'arg'}: {_resolve_type_name(p_el, by_id)}")
            ic.methods.append(ImportedMethod(
                name=op_name,
                return_type=_resolve_return_type(op_el, by_id),
                visibility=_VISIBILITY_FROM_XMI.get(op_el.get("visibility") or "public", "+"),
                is_static=op_el.get("isStatic") == "true",
                is_abstract=op_el.get("isAbstract") == "true",
                params=", ".join(params),
            ))
        # Modelo de datos: la PK es obligatoria, y las columnas FK no se
        # importan como atributos -- la relacion (asociacion «FK») ya las
        # representa y el backend generado crea esa columna a partir de ella.
        if pk_columns or fk_columns:
            ic.attributes = [a for a in ic.attributes if a.name not in fk_columns or a.name in pk_columns]
            for a in ic.attributes:
                if a.name in pk_columns:
                    a.required = True
        classes_by_id[xid] = ic
        name_by_id[xid] = name

    if not classes_by_id:
        result.warnings.append("No se encontro ninguna uml:Class en el archivo.")

    # --- Herencia (generalization, vive dentro de la clase hija) ---
    for el in tree.iter():
        if _xmi_type(el) not in ("uml:Class", "uml:Interface", "uml:Enumeration"):
            continue
        child_id = _xmi_id(el)
        child_name = name_by_id.get(child_id)
        if not child_name:
            continue
        for real_el in el:
            if _local(real_el.tag) != "interfaceRealization":
                continue
            iface_id = real_el.get("contract") or real_el.get("supplier")
            iface_name = name_by_id.get(iface_id) if iface_id else None
            if iface_name:
                result.relations.append(ImportedRelation(
                    from_name=child_name, to_name=iface_name, type="REALIZATION",
                    src_mult_min=1, src_mult_max=1, dst_mult_min=1, dst_mult_max=1,
                ))
        for gen_el in el:
            if _local(gen_el.tag) != "generalization":
                continue
            parent_id = gen_el.get("general")
            parent_name = name_by_id.get(parent_id) if parent_id else None
            if not parent_name and parent_id in by_id:
                parent_name = by_id[parent_id].get("name")
            if parent_name:
                result.relations.append(ImportedRelation(
                    from_name=child_name, to_name=parent_name, type="INHERITANCE",
                    src_mult_min=1, src_mult_max=1, dst_mult_min=1, dst_mult_max=1,
                ))
            else:
                result.warnings.append(f"Herencia de '{child_name}' con padre no resoluble, se omitio.")

    # --- Realizaciones sueltas (uml:Realization / uml:InterfaceRealization fuera de la clase) ---
    seen_real = {(r.from_name, r.to_name) for r in result.relations if r.type == "REALIZATION"}
    for el in tree.iter():
        if _xmi_type(el) not in ("uml:Realization", "uml:InterfaceRealization"):
            continue
        if _local(el.tag) == "interfaceRealization":
            continue  # ya leída dentro de su clase
        client, supplier = el.get("client"), el.get("supplier") or el.get("contract")
        c_name, s_name = name_by_id.get(client), name_by_id.get(supplier)
        if c_name and s_name and (c_name, s_name) not in seen_real:
            seen_real.add((c_name, s_name))
            result.relations.append(ImportedRelation(
                from_name=c_name, to_name=s_name, type="REALIZATION",
                src_mult_min=1, src_mult_max=1, dst_mult_min=1, dst_mult_max=1,
            ))

    # --- Dependencias ---
    for el in tree.iter():
        if _xmi_type(el) != "uml:Dependency":
            continue
        client = el.get("client")
        supplier = el.get("supplier")
        client_name = name_by_id.get(client) or (by_id.get(client).get("name") if client in by_id else None)
        supplier_name = name_by_id.get(supplier) or (by_id.get(supplier).get("name") if supplier in by_id else None)
        if client_name and supplier_name:
            result.relations.append(ImportedRelation(
                from_name=client_name, to_name=supplier_name, type="DEPENDENCY",
                label=el.get("name"),
                src_mult_min=1, src_mult_max=1, dst_mult_min=1, dst_mult_max=1,
            ))

    # Marca que uml:Association tiene una clase de asociacion vinculada:
    # el vinculo NO vive en el modelo UML (uml:Association no referencia a
    # la clase en absoluto), sino en xmi:Extension/connectors/connector,
    # como el atributo extendedProperties[@associationclass] -- verificado
    # contra un archivo real de EA. Un xmi:Association sin conector
    # correspondiente ahi (o sin ese atributo) es una asociacion comun.
    association_class_name: dict[str, str] = {}
    for el in tree.iter():
        if _local(el.tag) != "connector":
            continue
        for child in el:
            if _local(child.tag) != "extendedProperties":
                continue
            assoc_class_id = child.get("associationclass")
            if not assoc_class_id:
                continue
            conn_id = _xmi_id(el)
            if not conn_id:
                for key, val in el.attrib.items():
                    if _local(key) == "idref":
                        conn_id = val
                        break
            class_name = name_by_id.get(assoc_class_id)
            if conn_id and class_name:
                association_class_name[conn_id] = class_name

    # Direccion de cada conector segun Enterprise Architect
    # (xmi:Extension/connectors/connector/source|target): en sus archivos
    # el orden de los extremos de uml:Association no indica cual es el
    # origen, y sin esto algunas asociaciones volvian invertidas.
    # (clase de origen, clase de destino, multiplicidad del origen); la
    # multiplicidad desempata las asociaciones recursivas (mismo tipo en
    # los dos extremos).
    ea_direction: dict[str, tuple[str, str, str | None]] = {}
    for el in tree.iter():
        if _local(el.tag) != "connector":
            continue
        conn_id = next((v for k, v in el.attrib.items() if _local(k) == "idref"), None)
        ends_ids, source_mult = {}, None
        for child in el:
            if _local(child.tag) in ("source", "target"):
                ends_ids[_local(child.tag)] = next((v for k, v in child.attrib.items() if _local(k) == "idref"), None)
                if _local(child.tag) == "source":
                    t = next((g for g in child if _local(g.tag) == "type"), None)
                    source_mult = t.get("multiplicity") if t is not None else None
        if conn_id and ends_ids.get("source") and ends_ids.get("target"):
            ea_direction[conn_id] = (ends_ids["source"], ends_ids["target"], source_mult)

    # --- Asociaciones (incluye agregacion/composicion via aggregation="shared"/"composite") ---
    # uml:AssociationClass se procesa en el MISMO bucle que uml:Association:
    # a diferencia de lo que sugeria la extension de EA (el atributo
    # associationclass en xmi:Extension/connectors), en este archivo real
    # la AssociationClass trae sus propios ownedEnd apuntando directo a las
    # 2 clases "reales" -- no hace falta un uml:Association aparte ni el
    # connector para saber con que esta conectada.
    for el in tree.iter():
        el_type = _xmi_type(el)
        if el_type not in ("uml:Association", "uml:AssociationClass"):
            continue

        ends = [c for c in el if _local(c.tag) == "ownedEnd"]
        if len(ends) < 2:
            # Estilo alternativo: memberEnd apunta a Property definidas afuera
            # (a veces dentro de cada clase en vez de en la asociacion).
            end_ids = [c.get(f"{{{XMI_NS}}}idref") for c in el if _local(c.tag) == "memberEnd"]
            ends = [by_id[i] for i in end_ids if i in by_id]

        if len(ends) != 2:
            result.warnings.append(
                f"Asociacion '{el.get('name') or _xmi_id(el)}' con extremos no resolubles, se omitio."
            )
            continue

        def _end_class_name(end: ET.Element) -> str | None:
            type_id = end.get("type")
            if type_id and type_id in name_by_id:
                return name_by_id[type_id]
            for child in end:
                if _local(child.tag) == "type":
                    idref = child.get(f"{{{XMI_NS}}}idref") or child.get("href", "").rsplit("#", 1)[-1]
                    return name_by_id.get(idref)
            return None

        def _end_mult(end: ET.Element) -> tuple[int, int | None]:
            lo, hi = 1, 1
            for child in end:
                tag = _local(child.tag)
                if tag == "lowerValue":
                    try:
                        lo = int(child.get("value", "1"))
                    except ValueError:
                        lo = 1
                elif tag == "upperValue":
                    v = child.get("value", "1")
                    hi = None if v in ("*", "-1") else int(v) if v.isdigit() else 1
            return lo, hi

        # El extremo marcado con aggregation es el de la PARTE (UML, y asi lo
        # escribe EA); en el editor la parte es el origen. Sin marca, se
        # respeta el orden del archivo.
        def _end_type_id(end: ET.Element) -> str | None:
            if end.get("type"):
                return end.get("type")
            for child in end:
                if _local(child.tag) == "type":
                    return child.get(f"{{{XMI_NS}}}idref") or child.get("href", "").rsplit("#", 1)[-1]
            return None

        agg_ends = [e for e in ends if e.get("aggregation", "none") != "none"]
        if agg_ends:
            part = agg_ends[0]
            ends = [part, ends[1] if ends[0] is part else ends[0]]
        elif _xmi_id(el) in ea_direction:
            source_id, target_id, source_mult = ea_direction[_xmi_id(el)]
            if source_id != target_id:
                if _end_type_id(ends[1]) == source_id and _end_type_id(ends[0]) != source_id:
                    ends = [ends[1], ends[0]]
            elif source_mult:
                def _mult_text(end):
                    lo, hi = _end_mult(end)
                    return f"{lo}..{'*' if hi is None else hi}"
                if _mult_text(ends[0]) != source_mult and _mult_text(ends[1]) == source_mult:
                    ends = [ends[1], ends[0]]
        agg = ends[0].get("aggregation", "none")

        src_name = _end_class_name(ends[0])
        dst_name = _end_class_name(ends[1])
        if not src_name or not dst_name:
            result.warnings.append(
                f"Asociacion '{el.get('name') or _xmi_id(el)}' referencia una clase que no se pudo resolver, se omitio."
            )
            continue

        rel_type = _TYPE_BY_AGGREGATION.get(agg, RelType.ASSOCIATION).value
        src_min, src_max = _end_mult(ends[0])
        dst_min, dst_max = _end_mult(ends[1])

        # Nombre de la clase intermedia: para una AssociationClass real
        # (verificado contra un archivo de EA real), es su propio "name",
        # y sus ownedEnd apuntan directo a las 2 clases con las que se
        # conecta -- no hace falta ningun otro vinculo externo. El
        # association_class_name (via xmi:Extension/connectors) queda
        # como fallback para el caso en que el conector sea la unica
        # pista disponible (sin verificar contra un archivo real asi).
        assoc_class_name = el.get("name") if el_type == "uml:AssociationClass" else association_class_name.get(_xmi_id(el))
        if assoc_class_name and rel_type == "ASSOCIATION":
            # El modelo de este proyecto no representa la clase de
            # asociacion como un flag sobre una unica asociacion directa
            # entre las dos clases originales (asi es como EA la guarda
            # en el XMI): en cambio, necesita DOS relaciones punteadas,
            # cada una de una clase original hacia la clase intermedia.
            # Se sintetizan aca, en vez de importar la asociacion directa
            # que trae el archivo, para que el resultado coincida con lo
            # que produce convertToAssociationClass() en el frontend.
            result.relations.append(ImportedRelation(
                from_name=src_name, to_name=assoc_class_name, type="ASSOCIATION",
                src_mult_min=1, src_mult_max=1, dst_mult_min=0, dst_mult_max=None,
                es_clase_asociacion=True,
            ))
            result.relations.append(ImportedRelation(
                from_name=assoc_class_name, to_name=dst_name, type="ASSOCIATION",
                src_mult_min=0, src_mult_max=None, dst_mult_min=1, dst_mult_max=1,
                es_clase_asociacion=True,
            ))
            continue

        navigable_ids = {
            next((v for k, v in c.attrib.items() if _local(k) == "idref"), None)
            for c in el if _local(c.tag) == "navigableOwnedEnd"
        }
        result.relations.append(ImportedRelation(
            from_name=src_name, to_name=dst_name, type=rel_type,
            label=el.get("name"),
            src_mult_min=src_min, src_mult_max=src_max,
            dst_mult_min=dst_min, dst_mult_max=dst_max,
            src_role=ends[0].get("name") or None,
            dst_role=ends[1].get("name") or None,
            src_navigable=_xmi_id(ends[0]) in navigable_ids,
            dst_navigable=_xmi_id(ends[1]) in navigable_ids,
        ))

    result.classes = list(classes_by_id.values())
    return result
