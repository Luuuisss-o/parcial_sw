"""
Tests de exporters/generators/uap_generator.py

Corren el generador sobre el fixture fijo (Cliente, Producto, Pedido) y
verifican, por substring sobre el Java generado, que la estructura del
protocolo UAP es la esperada -- NO compilan el Java (eso requiere Maven
real, fuera del alcance de estos tests unitarios; ver README/plan).
"""
import os

import pytest

from exporters.generators.uap_generator import generate_uap

ENTITIES = ["cliente", "producto", "pedido"]
VERBS = ["create", "list", "get", "update", "delete"]


@pytest.fixture
def generated_dir(tmp_path, diagram_tienda_path):
    out_dir = tmp_path / "uap_out"
    generate_uap(diagram_tienda_path, str(out_dir), templates_dir="exporters/templates")
    return out_dir


def _read(generated_dir, filename: str) -> str:
    path = generated_dir / filename
    assert path.exists(), f"no se genero {filename}"
    return path.read_text(encoding="utf-8")


def test_generates_all_expected_files(generated_dir):
    expected = {
        "UapManifestController.java",
        "UapSchemaController.java",
        "UapToolsController.java",
        "UapToolDispatcher.java",
        "UapSyncController.java",
        "UapGeneration.java",
        "UapChangeLog.java",
        "UapCoerce.java",
        "JacksonTimeZoneConfig.java",
    }
    actual = {p.name for p in generated_dir.iterdir()}
    assert expected == actual


@pytest.mark.parametrize("entity", ENTITIES)
@pytest.mark.parametrize("verb", VERBS)
def test_dispatcher_has_a_case_for_every_entity_and_verb(generated_dir, entity, verb):
    dispatcher = _read(generated_dir, "UapToolDispatcher.java")
    assert f'case "{verb}_{entity}":' in dispatcher


def test_dispatcher_coerces_decimal_field_with_bigdecimal(generated_dir):
    dispatcher = _read(generated_dir, "UapToolDispatcher.java")
    # Producto.precio es "decimal" en el fixture -> debe coercionar con
    # asBigDecimal, nunca con asDouble/asString (perderia precision).
    assert "setPrecio(UapCoerce.asBigDecimal(" in dispatcher


def test_dispatcher_coerces_int_field_with_integer(generated_dir):
    dispatcher = _read(generated_dir, "UapToolDispatcher.java")
    # Producto.stock es "int" en el fixture.
    assert "setStock(UapCoerce.asInteger(" in dispatcher


def test_dispatcher_coerces_boolean_field(generated_dir):
    dispatcher = _read(generated_dir, "UapToolDispatcher.java")
    # Cliente.activo es "boolean" en el fixture.
    assert "setActivo(UapCoerce.asBoolean(" in dispatcher


def test_dispatcher_coerces_date_field(generated_dir):
    dispatcher = _read(generated_dir, "UapToolDispatcher.java")
    # Pedido.fecha es "date" en el fixture.
    assert "setFecha(UapCoerce.asLocalDate(" in dispatcher


def test_dispatcher_never_uses_reflection():
    """Requisito duro y explicito del usuario: ninguna invocacion de tool
    puede resolverse via reflexion en runtime. Se testea sobre el
    directorio completo generado, no solo el dispatcher, por si algun otro
    archivo UAP llegara a usarla."""
    import tempfile
    from exporters.generators.uap_generator import generate_uap

    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "uap")
        generate_uap(
            "exporters/tests/fixtures/diagram_tienda.json",
            out,
            templates_dir="exporters/templates",
        )
        forbidden = ["getDeclaredMethod", "Class.forName", "Method.invoke", "setAccessible"]
        for filename in os.listdir(out):
            content = open(os.path.join(out, filename), encoding="utf-8").read()
            for pattern in forbidden:
                assert pattern not in content, f"{filename} usa reflexion ({pattern}), esta prohibido"


def _method_body(source: str, method_name: str) -> str:
    """Extrae el cuerpo de una private Map<String, Object> tool_X() de
    UapToolsController.java, buscando la DEFINICION del metodo (con
    "private Map") en vez de la primera mencion de su nombre -- el archivo
    tambien lista cada tool en tools()/list.add(tool_X()), que aparece
    antes de la definicion y haria matchear el lugar equivocado."""
    marker = f"private Map<String, Object> {method_name}()"
    start = source.index(marker)
    end = source.index("\n    }\n", start)
    return source[start:end]


def test_id_field_is_read_only_in_schema_and_absent_from_create_tool(generated_dir):
    schema = _read(generated_dir, "UapSchemaController.java")
    tools = _read(generated_dir, "UapToolsController.java")
    assert 'field.put("readOnly", true);' in schema
    # El input de create_cliente no debe incluir "id" entre sus properties:
    # se arma solo con writable_fields, que excluyen el id_field.
    create_block = _method_body(tools, "tool_create_cliente")
    assert '"id"' not in create_block


def test_required_field_appears_in_create_tool_required_list(generated_dir):
    tools = _read(generated_dir, "UapToolsController.java")
    create_block = _method_body(tools, "tool_create_cliente")
    # Cliente.nombre es required=true en el fixture.
    assert '"nombre"' in create_block


def test_manifest_lists_all_entities_with_aliases(generated_dir):
    manifest = _read(generated_dir, "UapManifestController.java")
    for entity in ENTITIES:
        assert f'"{entity}"' in manifest
    assert '"productos"' in manifest  # plural


def test_generate_uap_reloads_json_independently(diagram_tienda_path, tmp_path):
    """generate_uap no debe depender de que otro generador haya cargado y
    mutado el mismo dict antes -- tiene que poder correr solo, cargando su
    propio JSON, igual que el resto del pipeline (ver api_layer.py)."""
    out_dir = tmp_path / "solo"
    generate_uap(diagram_tienda_path, str(out_dir), templates_dir="exporters/templates")
    assert (out_dir / "UapManifestController.java").exists()
