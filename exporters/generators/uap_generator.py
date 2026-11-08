"""
uap_generator.py
Genera el protocolo UAP (Universal Assistant Protocol) para el backend
Spring Boot exportado: un conjunto de endpoints que exponen, de forma
descubrible en runtime, las mismas entidades que ya generan
json_to_full_orm/model_to_dto/service_to_controller -- sin inventar ningun
dominio nuevo. Un cliente generico (el asistente de IA local del movil)
puede leer /uap/v1/manifest y /uap/v1/tools de CUALQUIER backend generado
por el diagramador y saber que operaciones puede ofrecer, sin que se le
haya programado nada especifico para ese diagrama.

Principio de diseño: todo lo que UAP publica (tipos de campo, si un ID es
requerido, que atributos existen) se deriva del MISMO JSON que ya alimenta
los otros generadores, pasando siempre por las mismas funciones
(map_type/map_json_schema/to_camel) para que el contrato publicado nunca
pueda divergir del codigo Java que realmente se genera al lado.

La invocacion de tools (POST /uap/v1/tools/{toolId}/invoke) se resuelve con
un switch de Java generado en tiempo de build (ver uap_tool_dispatcher.java.j2)
-- nunca con reflexion en runtime. Esto es una restriccion de seguridad
explicita: un backend generado no puede exponer un mecanismo que ejecute
"cualquier metodo cuyo nombre coincida", porque eso es indistinguible de una
puerta trasera. El precio de esa decision es que agregar una entidad nueva
implica regenerar el proyecto (que es exactamente lo que ya pasa hoy con
los controllers/services/repositories existentes).
"""
import os
import json

from jinja2 import Environment, FileSystemLoader

from exporters.generators.json_to_relations import to_camel
from exporters.generators.type_mapping import map_type, map_json_schema

# Los 5 verbos CRUD que UAP publica por entidad. "list"/"get" no reciben
# body (son GET-like en semantica de tool, aunque el invoke real es siempre
# POST /uap/v1/tools/{toolId}/invoke por uniformidad del protocolo).
_VERBS = ("create", "list", "get", "update", "delete")

# JSON-Schema type/format -> metodo estatico de UapCoerce (ver
# uap_coerce.java.j2). Determina, para cada campo escribible, que
# conversion server-side aplicar sobre el valor crudo que llega en el JSON
# del invoke -- nunca se confia en que el cliente mando el tipo correcto.
_COERCE_METHOD_BY_SCHEMA = {
    ("integer", "int32"): "asInteger",
    ("integer", "int64"): "asLong",
    ("number", None): "asDouble",
    ("number", "decimal"): "asBigDecimal",
    ("boolean", None): "asBoolean",
    ("string", "date"): "asLocalDate",
    ("string", "date-time"): "asLocalDateTime",
    ("string", None): "asString",
}


def _coerce_method_for(json_schema: dict) -> str:
    key = (json_schema.get("type"), json_schema.get("format"))
    return _COERCE_METHOD_BY_SCHEMA.get(key, "asString")

_TEMPLATE_FILES = {
    "manifest": "uap_manifest_controller.java.j2",
    "schema": "uap_schema_controller.java.j2",
    "tools": "uap_tools_controller.java.j2",
    "dispatcher": "uap_tool_dispatcher.java.j2",
    "sync": "uap_sync_controller.java.j2",
    "generation_entity": "uap_generation_entity.java.j2",
    "changelog_entity": "uap_changelog_entity.java.j2",
    "coerce": "uap_coerce.java.j2",
    "jackson_config": "uap_jackson_config.java.j2",
}

_OUTPUT_FILES = {
    "manifest": "UapManifestController.java",
    "schema": "UapSchemaController.java",
    "tools": "UapToolsController.java",
    "dispatcher": "UapToolDispatcher.java",
    "sync": "UapSyncController.java",
    "generation_entity": "UapGeneration.java",
    "changelog_entity": "UapChangeLog.java",
    "coerce": "UapCoerce.java",
    "jackson_config": "JacksonTimeZoneConfig.java",
}


def _build_entity_model(class_def: dict) -> dict:
    """Arma el modelo intermedio de una clase del diagrama para los
    templates UAP. Replica EXACTAMENTE la regla de id de
    json_to_full_orm.generate_entity: si no hay atributo "id", se inserta
    uno; y si existe, se fuerza a Long -- el esquema/tools de UAP tienen
    que describir la entidad tal cual el ORM la genera de verdad, nunca
    prometer un tipo de id (ej. UUID) que el generador de entidades no
    produce hoy."""
    class_name = class_def["name"]
    # Copia superficial de attributes: no mutamos el dict del caller, cada
    # generador del pipeline carga su propio JSON (ver docstring del modulo)
    # pero por las dudas de que en el futuro alguien pase el mismo dict
    # cargado una sola vez a varios generadores.
    attributes = [dict(a) for a in class_def.get("attributes", [])]

    has_id = any(to_camel(a["name"]).lower() == "id" for a in attributes)
    if not has_id:
        attributes.insert(0, {"name": "id", "type": "long", "required": True})

    fields = []
    for attr in attributes:
        name = to_camel(attr["name"])
        is_id = name.lower() == "id"
        java_type = "Long" if is_id else map_type(attr["type"])
        json_schema = {"type": "integer", "format": "int64"} if is_id else map_json_schema(attr["type"])
        fields.append({
            "name": name,
            "java_type": java_type,
            "json_schema": json_schema,
            "required": bool(attr.get("required", False)) and not is_id,
            "is_id": is_id,
            "getter": f"get{name[0].upper()}{name[1:]}",
            "setter": f"set{name[0].upper()}{name[1:]}",
            "coerce_method": _coerce_method_for(json_schema),
        })

    entity_key = class_name.lower()
    return {
        "class_name": class_name,
        "entity_key": entity_key,
        "plural": entity_key + "s",
        "fields": fields,
        # Campos no-id, los unicos que create/update aceptan en el body.
        "writable_fields": [f for f in fields if not f["is_id"]],
        "id_field": next(f for f in fields if f["is_id"]),
    }


def _tool_id(verb: str, entity_key: str) -> str:
    return f"{verb}_{entity_key}"


def generate_uap(json_path: str, output_dir: str, templates_dir: str = "../templates") -> None:
    """Genera los archivos Java del protocolo UAP en output_dir (se espera
    src/main/java/com/test/uap/, ver project_builder.py). Carga su propio
    JSON del diagrama, igual que el resto de los generadores del pipeline."""
    os.makedirs(output_dir, exist_ok=True)

    env = Environment(loader=FileSystemLoader(templates_dir), trim_blocks=True, lstrip_blocks=True)

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    diagram = data["diagram"]

    entities = [_build_entity_model(c) for c in diagram["classes"]]

    # Cada entidad ofrece sus 5 tools con el inputSchema derivado de sus
    # propios campos -- create/update sin el id (autogenerado / se pasa por
    # la URL, no por el body), list sin campos (solo pagina), get/delete
    # solo con el id.
    tools = []
    for e in entities:
        writable_props = {f["name"]: f["json_schema"] for f in e["writable_fields"]}
        required_writable = [f["name"] for f in e["writable_fields"] if f["required"]]
        id_props = {e["id_field"]["name"]: e["id_field"]["json_schema"]}

        tools.append({
            "tool_id": _tool_id("create", e["entity_key"]),
            "entity_key": e["entity_key"],
            "verb": "create",
            "description": f"Crea un/a {e['class_name']} nuevo/a.",
            "input_schema": {"type": "object", "properties": writable_props, "required": required_writable},
        })
        tools.append({
            "tool_id": _tool_id("list", e["entity_key"]),
            "entity_key": e["entity_key"],
            "verb": "list",
            "description": f"Lista los/las {e['plural']} existentes.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        })
        tools.append({
            "tool_id": _tool_id("get", e["entity_key"]),
            "entity_key": e["entity_key"],
            "verb": "get",
            "description": f"Consulta un/a {e['class_name']} por id.",
            "input_schema": {"type": "object", "properties": id_props, "required": [e["id_field"]["name"]]},
        })
        tools.append({
            "tool_id": _tool_id("update", e["entity_key"]),
            "entity_key": e["entity_key"],
            "verb": "update",
            "description": f"Actualiza un/a {e['class_name']} existente.",
            "input_schema": {
                "type": "object",
                "properties": {**id_props, **writable_props},
                "required": [e["id_field"]["name"]],
            },
        })
        tools.append({
            "tool_id": _tool_id("delete", e["entity_key"]),
            "entity_key": e["entity_key"],
            "verb": "delete",
            "description": f"Elimina un/a {e['class_name']} por id.",
            "input_schema": {"type": "object", "properties": id_props, "required": [e["id_field"]["name"]]},
        })

    context = {
        "entities": entities,
        "tools": tools,
        "backend_name": diagram.get("title", "demo"),
    }

    for key, template_file in _TEMPLATE_FILES.items():
        template = env.get_template(template_file)
        code = template.render(**context)
        out_path = os.path.join(output_dir, _OUTPUT_FILES[key])
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(code)
        print(f"Generado UAP: {out_path}")
