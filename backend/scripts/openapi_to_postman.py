"""Convierte openapi.json (generado por FastAPI) a una colección Postman v2.1.

No depende de herramientas externas (npx, etc.): recorre el schema OpenAPI a
mano y arma la colección + un environment con `base_url` y `access_token`.
Uso:
    ./.venv/Scripts/python.exe scripts/openapi_to_postman.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OPENAPI_PATH = ROOT / "openapi.json"
COLLECTION_PATH = ROOT / "postman" / "UML_AI_Tool_API.postman_collection.json"
ENVIRONMENT_PATH = ROOT / "postman" / "UML_AI_Tool_Local.postman_environment.json"

VAR_RE = re.compile(r"\{([^{}]+)\}")


def to_postman_path(path: str) -> tuple[list[str], list[dict]]:
    """'/diagrams/{diagram_id}' -> (['diagrams', ':diagram_id'], [path var def])."""
    segments = []
    variables = []
    for part in path.strip("/").split("/"):
        m = VAR_RE.fullmatch(part)
        if m:
            name = m.group(1)
            segments.append(f":{name}")
            variables.append({"key": name, "value": ""})
        else:
            segments.append(part)
    return segments, variables


def build_body(operation: dict, schemas: dict) -> dict | None:
    request_body = operation.get("requestBody")
    if not request_body:
        return None
    content = request_body.get("content", {})
    json_content = content.get("application/json")
    if not json_content:
        return None
    schema = json_content.get("schema", {})
    example = schema_to_example(schema, schemas)
    return {
        "mode": "raw",
        "raw": json.dumps(example, indent=2, ensure_ascii=False),
        "options": {"raw": {"language": "json"}},
    }


def resolve_ref(ref: str, schemas: dict) -> dict:
    name = ref.split("/")[-1]
    return schemas.get(name, {})


def schema_to_example(schema: dict, schemas: dict, depth: int = 0) -> object:
    if depth > 6:
        return None
    if "$ref" in schema:
        return schema_to_example(resolve_ref(schema["$ref"], schemas), schemas, depth + 1)

    if "example" in schema:
        return schema["example"]

    schema_type = schema.get("type")

    if schema_type == "object" or "properties" in schema:
        result = {}
        for prop_name, prop_schema in schema.get("properties", {}).items():
            result[prop_name] = schema_to_example(prop_schema, schemas, depth + 1)
        return result

    if schema_type == "array":
        item_schema = schema.get("items", {})
        return [schema_to_example(item_schema, schemas, depth + 1)]

    if schema_type == "string":
        fmt = schema.get("format")
        if fmt == "email":
            return "usuario@example.com"
        if fmt in ("date-time",):
            return "2025-01-01T00:00:00Z"
        if fmt == "uuid":
            return "00000000-0000-0000-0000-000000000000"
        if schema.get("enum"):
            return schema["enum"][0]
        return schema.get("default", "string")

    if schema_type == "integer":
        return schema.get("default", 0)

    if schema_type == "number":
        return schema.get("default", 0)

    if schema_type == "boolean":
        return schema.get("default", False)

    # anyOf / oneOf: usar la primera opción no nula
    for key in ("anyOf", "oneOf"):
        options = schema.get(key)
        if options:
            for opt in options:
                if opt.get("type") != "null":
                    return schema_to_example(opt, schemas, depth + 1)

    return None


def build_query_params(operation: dict) -> list[dict]:
    params = []
    for p in operation.get("parameters", []):
        if p.get("in") != "query":
            continue
        params.append(
            {
                "key": p["name"],
                "value": str(p.get("schema", {}).get("default", "")),
                "description": p.get("description", ""),
                "disabled": not p.get("required", False),
            }
        )
    return params


def needs_auth(operation: dict) -> bool:
    return bool(operation.get("security"))


def build_item(method: str, path: str, operation: dict, schemas: dict) -> dict:
    segments, path_vars = to_postman_path(path)
    query_params = build_query_params(operation)
    body = build_body(operation, schemas)

    request: dict = {
        "method": method.upper(),
        "header": [{"key": "Content-Type", "value": "application/json"}] if body else [],
        "url": {
            "raw": "{{base_url}}/" + "/".join(segments) + (
                "?" + "&".join(f"{q['key']}={q['value']}" for q in query_params) if query_params else ""
            ),
            "host": ["{{base_url}}"],
            "path": segments,
        },
    }
    if path_vars:
        request["url"]["variable"] = path_vars
    if query_params:
        request["url"]["query"] = query_params
    if body:
        request["body"] = body
    if needs_auth(operation):
        request["auth"] = {"type": "bearer", "bearer": [{"key": "token", "value": "{{access_token}}", "type": "string"}]}

    return {
        "name": operation.get("summary") or f"{method.upper()} {path}",
        "request": request,
        "response": [],
    }


def main() -> None:
    spec = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    schemas = spec.get("components", {}).get("schemas", {})

    folders: dict[str, list[dict]] = {}
    for path, methods in spec["paths"].items():
        for method, operation in methods.items():
            if method not in ("get", "post", "patch", "put", "delete"):
                continue
            tags = operation.get("tags") or ["general"]
            folder = tags[0]
            folders.setdefault(folder, []).append(build_item(method, path, operation, schemas))

    collection = {
        "info": {
            "name": spec["info"]["title"],
            "description": "Generado automáticamente desde /openapi.json. Correr primero 'Auth > Sign in' para setear {{access_token}} (ver Tests script de ese request).",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": [{"name": folder, "item": items} for folder, items in folders.items()],
        "variable": [
            {"key": "base_url", "value": "http://localhost:8000"},
            {"key": "access_token", "value": ""},
        ],
    }

    # Al request de sign-in le agregamos un test script que guarda el token
    # devuelto en la variable de entorno {{access_token}}, para no copiarlo
    # a mano en cada request protegido.
    for folder in collection["item"]:
        if folder["name"].lower() != "auth":
            continue
        for item in folder["item"]:
            if "sign-in" in item["request"]["url"]["raw"]:
                item["event"] = [
                    {
                        "listen": "test",
                        "script": {
                            "type": "text/javascript",
                            "exec": [
                                "const data = pm.response.json();",
                                "if (data.access_token) {",
                                "    pm.collectionVariables.set('access_token', data.access_token);",
                                "}",
                            ],
                        },
                    }
                ]

    COLLECTION_PATH.parent.mkdir(exist_ok=True)
    COLLECTION_PATH.write_text(json.dumps(collection, indent=2, ensure_ascii=False), encoding="utf-8")

    environment = {
        "id": "uml-ai-tool-local",
        "name": "UML AI Tool - Local",
        "values": [
            {"key": "base_url", "value": "http://localhost:8000", "enabled": True},
            {"key": "access_token", "value": "", "enabled": True},
        ],
        "_postman_variable_scope": "environment",
    }
    ENVIRONMENT_PATH.write_text(json.dumps(environment, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Colección: {COLLECTION_PATH}")
    print(f"Environment: {ENVIRONMENT_PATH}")


if __name__ == "__main__":
    main()
