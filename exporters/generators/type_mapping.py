# exporters/generators/type_mapping.py
"""
Mapeo unico UML -> tipo Java, usado por todos los generadores (entidades,
DTOs, etc).

Antes cada generador tenia su propia copia de este diccionario, y las
copias solo reconocian claves en minuscula sin alias ("int", "double",
"string"...). El asistente de IA crea atributos con tipos al estilo Java
("Integer", "Double", "Boolean", con mayuscula), y el editor manual usa
nombres UML en minuscula ("int", "decimal", "text"...). Como el lookup no
normalizaba may/min ni conocia los alias, cualquier tipo que no calzara
letra por letra cafa en el default "String" sin avisar -- un atributo
"stock" de tipo Integer terminaba generado como `private String stock;`.
"""

_MAPPING = {
    # UML clasico (lo que ofrece el selector del Inspector)
    "int": "Integer",
    "long": "Long",
    "string": "String",
    "text": "String",
    "float": "Float",
    "double": "Double",
    "decimal": "java.math.BigDecimal",
    "boolean": "Boolean",
    "date": "LocalDate",
    "datetime": "LocalDateTime",
    "uuid": "String",
    "email": "String",

    # Alias que puede generar el asistente de IA (tipos "estilo Java")
    "integer": "Integer",
    "bool": "Boolean",
    "localdate": "LocalDate",
    "localdatetime": "LocalDateTime",
    "timestamp": "LocalDateTime",
    "bigdecimal": "java.math.BigDecimal",
}


def map_type(attr_type: str) -> str:
    """Traduce un tipo UML/atributo (en cualquier capitalizacion conocida)
    al tipo Java correspondiente. Si no se reconoce, cae a String."""
    if not attr_type:
        return "String"
    return _MAPPING.get(attr_type.strip().lower(), "String")


# Tipo Java -> nodo JSON-Schema, para el protocolo UAP (ver uap_generator.py).
# Mapea SIEMPRE a partir del tipo Java ya resuelto por map_type() en vez de
# tener su propia copia del diccionario UML->algo: si hubiera dos mapeos
# independientes, uno se desincroniza del otro tarde o temprano y el schema
# que UAP publica termina mintiendo sobre el tipo Java real de la entidad
# generada (justo el bug que el docstring de arriba explica que ya paso una
# vez con map_type). Point unico de la verdad: _MAPPING.
_JSON_SCHEMA = {
    "Integer": {"type": "integer", "format": "int32"},
    "Long": {"type": "integer", "format": "int64"},
    "Float": {"type": "number"},
    "Double": {"type": "number"},
    "java.math.BigDecimal": {"type": "number", "format": "decimal"},
    "Boolean": {"type": "boolean"},
    "LocalDate": {"type": "string", "format": "date"},
    "LocalDateTime": {"type": "string", "format": "date-time"},
    "String": {"type": "string"},
}


def map_json_schema(attr_type: str) -> dict:
    """Traduce un tipo UML/atributo al nodo JSON-Schema correspondiente,
    para publicarlo en GET /uap/v1/schema. Tipo Java desconocido (no deberia
    pasar, _JSON_SCHEMA cubre todo lo que devuelve map_type) -> "string"."""
    java_type = map_type(attr_type)
    return dict(_JSON_SCHEMA.get(java_type, {"type": "string"}))
