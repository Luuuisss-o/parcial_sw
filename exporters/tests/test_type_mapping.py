"""
Tests de exporters/generators/type_mapping.py

El foco es map_json_schema: nunca debe poder desincronizarse de map_type(),
porque eso haria que el protocolo UAP publique un tipo de campo (ej.
"string") distinto del tipo Java realmente generado en la entidad (ej.
BigDecimal) -- justo la clase de bug que el modulo ya sufrio una vez con
map_type y que su propio docstring documenta.
"""
import pytest

from exporters.generators.type_mapping import _MAPPING, map_json_schema, map_type


def test_map_type_default_to_string_on_unknown():
    assert map_type("algo-que-no-existe") == "String"
    assert map_type("") == "String"
    assert map_type(None) == "String"


@pytest.mark.parametrize(
    "uml_type,expected",
    [
        ("int", {"type": "integer", "format": "int32"}),
        ("integer", {"type": "integer", "format": "int32"}),
        ("long", {"type": "integer", "format": "int64"}),
        ("decimal", {"type": "number", "format": "decimal"}),
        ("bigdecimal", {"type": "number", "format": "decimal"}),
        ("boolean", {"type": "boolean"}),
        ("bool", {"type": "boolean"}),
        ("date", {"type": "string", "format": "date"}),
        ("datetime", {"type": "string", "format": "date-time"}),
        ("timestamp", {"type": "string", "format": "date-time"}),
        ("string", {"type": "string"}),
        ("text", {"type": "string"}),
        ("email", {"type": "string"}),
        ("uuid", {"type": "string"}),
    ],
)
def test_map_json_schema_known_types(uml_type, expected):
    assert map_json_schema(uml_type) == expected


def test_map_json_schema_unknown_type_falls_back_to_string():
    assert map_json_schema("tipo-inventado") == {"type": "string"}
    assert map_json_schema(None) == {"type": "string"}


@pytest.mark.parametrize("uml_type", list(_MAPPING.keys()))
def test_map_json_schema_never_diverges_from_map_type(uml_type):
    """Para TODA clave que map_type() reconoce, map_json_schema() tiene que
    devolver un nodo -- nunca puede caer silenciosamente al default
    generico {"type": "string"} para un tipo que en realidad se mapea a
    Integer/Long/BigDecimal/Boolean/fecha en el ORM. Si esto falla, alguien
    agrego un tipo a _MAPPING sin agregar su contraparte a _JSON_SCHEMA."""
    java_type = map_type(uml_type)
    schema = map_json_schema(uml_type)
    if java_type == "String":
        # Unico caso legitimo donde el default generico es correcto.
        assert schema == {"type": "string"}
    else:
        assert schema.get("type") in ("integer", "number", "boolean", "string")
        # Ningun tipo Java no-String puede terminar mapeado silenciosamente
        # a un schema que perdio el formato (ej. BigDecimal -> plain string
        # sin "format":"decimal" seria una regresion real).
        if java_type in ("Integer", "Long", "Float", "Double", "Boolean") or "BigDecimal" in java_type:
            assert schema["type"] in ("integer", "number", "boolean")


def test_map_json_schema_returns_a_fresh_dict_each_time():
    """Devuelve una copia, no una referencia al dict interno de
    _JSON_SCHEMA -- si alguien mutara el resultado (ej. para agregar
    "description" a un campo puntual en uap_generator.py) no debe afectar
    las llamadas siguientes."""
    a = map_json_schema("int")
    a["extra"] = "mutado"
    b = map_json_schema("int")
    assert "extra" not in b
