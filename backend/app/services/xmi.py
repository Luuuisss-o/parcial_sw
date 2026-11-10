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

_AGGREGATION_BY_TYPE = {
    RelType.COMPOSITION: "composite",
    RelType.AGGREGATION: "shared",
    RelType.ASSOCIATION: "none",
}
_TYPE_BY_AGGREGATION = {v: k for k, v in _AGGREGATION_BY_TYPE.items()}


def _mult(value: int | None) -> str:
    return "*" if value is None else str(value)


# =====================================================================
# Export: diagrama -> XMI
# =====================================================================
def build_xmi(diagram) -> bytes:
    root = ET.Element(f"{{{XMI_NS}}}XMI", {f"{{{XMI_NS}}}version": "2.1"})
    model = ET.SubElement(root, f"{{{UML_NS}}}Model", {
        f"{{{XMI_NS}}}type": "uml:Model",
        f"{{{XMI_NS}}}id": "model_1",
        "name": diagram.title or "diagram",
    })

    class_ids = {c.id: f"C_{c.id}" for c in diagram.classes}
    used_datatypes: dict[str, str] = {}  # clave en minuscula -> nombre del DataType

    for c in diagram.classes:
        el = ET.SubElement(model, "packagedElement", {
            f"{{{XMI_NS}}}type": "uml:Class",
            f"{{{XMI_NS}}}id": class_ids[c.id],
            "name": c.nombre,
        })
        for a in c.atributos:
            attr_el = ET.SubElement(el, "ownedAttribute", {
                f"{{{XMI_NS}}}type": "uml:Property",
                f"{{{XMI_NS}}}id": f"A_{a.id}",
                "name": a.nombre,
                "visibility": "private",
            })
            if a.requerido:
                attr_el.set("isNullable", "false")

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

        for m in c.metodos:
            op_el = ET.SubElement(el, "ownedOperation", {
                f"{{{XMI_NS}}}id": f"M_{m.id}",
                "name": m.nombre,
                "visibility": "public",
            })
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
        for r in c.outgoing_relations:
            if r.tipo == RelType.INHERITANCE:
                ET.SubElement(el, "generalization", {
                    f"{{{XMI_NS}}}id": f"G_{r.id}",
                    "general": class_ids[r.destino_id],
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
        if r.tipo == RelType.INHERITANCE:
            continue  # ya se exporto como generalization

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
        ET.SubElement(end1, "lowerValue", {f"{{{XMI_NS}}}type": "uml:LiteralInteger", "value": _mult(r.mult_origen_min)})
        ET.SubElement(end1, "upperValue", {f"{{{XMI_NS}}}type": "uml:LiteralUnlimitedNatural", "value": _mult(r.mult_origen_max)})

        end2 = ET.SubElement(assoc, "ownedEnd", {
            f"{{{XMI_NS}}}type": "uml:Property",
            f"{{{XMI_NS}}}id": f"E2_{r.id}",
            "type": class_ids[r.destino_id],
            "aggregation": "none",
        })
        ET.SubElement(end2, "lowerValue", {f"{{{XMI_NS}}}type": "uml:LiteralInteger", "value": _mult(r.mult_destino_min)})
        ET.SubElement(end2, "upperValue", {f"{{{XMI_NS}}}type": "uml:LiteralUnlimitedNatural", "value": _mult(r.mult_destino_max)})

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


@dataclass
class ImportedMethod:
    name: str
    return_type: str = "void"


@dataclass
class ImportedClass:
    xmi_id: str
    name: str
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
    return _FROM_UML_PRIMITIVE.get(key) or _FROM_LOCAL_DATATYPE.get(key) or raw


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

    # --- Clases + atributos ---
    # EA representa una clase de asociacion (UML 2.5: la relacion
    # muchos-a-muchos vista como clase propia) con xmi:type="uml:AssociationClass"
    # en vez de "uml:Class" -- verificado contra un archivo real exportado
    # desde EA con dos clases de asociacion genuinas. Sin este chequeo
    # extra, esas clases se descartaban por completo al importar (no solo
    # perdian el estilo de linea punteada: directamente desaparecian del
    # diagrama resultante).
    for el in tree.iter():
        if _xmi_type(el) not in ("uml:Class", "uml:AssociationClass"):
            continue
        xid = _xmi_id(el)
        name = el.get("name")
        if not xid or not name:
            continue
        ic = ImportedClass(xmi_id=xid, name=name)
        for attr_el in el:
            if _local(attr_el.tag) != "ownedAttribute":
                continue
            if _xmi_type(attr_el) not in (None, "uml:Property"):
                continue
            attr_name = attr_el.get("name")
            if not attr_name:
                continue
            required = attr_el.get("isNullable") == "false" or attr_el.get("required") == "true"
            ic.attributes.append(ImportedAttribute(
                name=attr_name,
                type=(_normalize_type(ext_attr_types[_xmi_id(attr_el)]) if _xmi_id(attr_el) in ext_attr_types
                      else _resolve_type_name(attr_el, by_id)),
                required=required,
            ))
        for op_el in el:
            if _local(op_el.tag) != "ownedOperation":
                continue
            op_name = op_el.get("name")
            if not op_name:
                continue
            ic.methods.append(ImportedMethod(
                name=op_name,
                return_type=_resolve_return_type(op_el, by_id),
            ))
        classes_by_id[xid] = ic
        name_by_id[xid] = name

    if not classes_by_id:
        result.warnings.append("No se encontro ninguna uml:Class en el archivo.")

    # --- Herencia (generalization, vive dentro de la clase hija) ---
    for el in tree.iter():
        if _xmi_type(el) != "uml:Class":
            continue
        child_id = _xmi_id(el)
        child_name = name_by_id.get(child_id)
        if not child_name:
            continue
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

        result.relations.append(ImportedRelation(
            from_name=src_name, to_name=dst_name, type=rel_type,
            label=el.get("name"),
            src_mult_min=src_min, src_mult_max=src_max,
            dst_mult_min=dst_min, dst_mult_max=dst_max,
        ))

    result.classes = list(classes_by_id.values())
    return result
