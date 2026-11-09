"""
api_layer.py
Genera la capa de API REST del backend: DTO, Service y Controller de cada
entidad, mas el manejo de errores comun (paquete `exceptions`).

Reemplaza a model_to_dto / repository_to_service / service_to_controller,
que generaban controladores que exponian la entidad JPA directamente:
  - GET /{id} devolvia un Optional serializado ({"present": true}),
  - las relaciones no se podian asignar (las entidades no tenian
    getters/setters para ellas) y un id inexistente devolvia 200 vacio,
  - los DTO se generaban pero no se usaban.

Contrato que se genera, por entidad (ej. Pedido -> /api/pedidos):
  - El DTO lleva el id, los atributos (incluidos los heredados) y las
    relaciones como ids: `clienteId` (a-uno) o `productoIds` (a-muchos).
    Solo las del lado DUENO de la relacion se pueden escribir; las del lado
    inverso (`mappedBy`) se devuelven pero se ignoran al recibir, porque JPA
    no persiste ese lado.
  - POST 201 / GET 200 / PUT 200 / DELETE 204; 404 si el id no existe; 400
    si falta un atributo obligatorio o se referencia un id inexistente; 409
    si borrar violaria una FK (ver ApiExceptionHandler).
  - El Service conserva los metodos sobre la entidad (findAll, findById,
    save, delete) que usa la capa UAP del movil (uap_tool_dispatcher).
"""

import json
import os

from jinja2 import Environment, FileSystemLoader

from exporters.generators.json_to_full_orm import build_entity
from exporters.generators.json_to_relations import build_relations, to_camel
from exporters.generators.type_mapping import map_type


def _cap(name: str) -> str:
    return name[0].upper() + name[1:]


def _parent_of(class_name: str, relations_map: dict) -> str | None:
    for rel in relations_map.get(class_name, {}).values():
        if rel.get("type") == "Extends":
            return rel.get("parent")
    return None


def build_api_models(json_path: str) -> list[dict]:
    """Metadatos por entidad para las plantillas de DTO/Service/Controller."""
    with open(json_path, "r", encoding="utf-8") as f:
        diagram = json.load(f)["diagram"]
    relations_map = build_relations(json_path)
    classes = {c["name"]: c for c in diagram["classes"]}

    own = {}
    for name, c in classes.items():
        attrs = []
        for a in c.get("attributes", []):
            field = to_camel(a["name"])
            if field.lower() == "id":
                continue
            attrs.append({
                "name": field,
                "cap": _cap(field),
                "type": map_type(a["type"]),
                "required": bool(a.get("required")),
            })
        _, rel_fields = build_entity(c, relations_map)
        own[name] = {"attrs": attrs, "rels": rel_fields, "parent": _parent_of(name, relations_map)}

    models = []
    for name in classes:
        # Atributos y relaciones heredados (el hijo extiende a la entidad
        # padre en Java, asi que tiene sus getters/setters).
        chain, cur, seen = [], name, set()
        while cur and cur in own and cur not in seen:
            seen.add(cur)
            chain.insert(0, cur)
            cur = own[cur]["parent"]
        attrs = [a for c in chain for a in own[c]["attrs"]]
        rels = []
        for c in chain:
            for r in own[c]["rels"]:
                dto_field = r["name"] + ("Ids" if r["is_list"] else "Id")
                rels.append({
                    **r,
                    "dto_field": dto_field,
                    "dto_cap": _cap(dto_field),
                    "repo_var": "repository" if r["target"] == name else to_camel(r["target"]) + "Repository",
                })
        targets = sorted({r["target"] for r in rels if r["owner"] and r["target"] != name})
        models.append({
            "class_name": name,
            "var": to_camel(name),
            "path": name.lower() + "s",
            "attrs": attrs,
            "rels": rels,
            "owner_rels": [r for r in rels if r["owner"]],
            "targets": [{"class_name": t, "var": to_camel(t) + "Repository"} for t in targets],
            "required_attrs": [a for a in attrs if a["required"]],
            # Un helper findAll<Destino> por clase destino de relaciones a-muchos.
            "list_targets": [
                {"class_name": t, "repo_var": "repository" if t == name else to_camel(t) + "Repository"}
                for t in sorted({r["target"] for r in rels if r["owner"] and r["is_list"]})
            ],
        })
    return models


def generate_api_layer(json_path: str, src_main: str, templates_dir: str) -> list[dict]:
    env = Environment(loader=FileSystemLoader(templates_dir), keep_trailing_newline=True)
    models = build_api_models(json_path)

    out = {
        "dtos": ("dto.java.j2", "{}Dto.java"),
        "services": ("service.java.j2", "{}Service.java"),
        "controllers": ("controller.java.j2", "{}Controller.java"),
    }
    for folder, (template_name, file_pattern) in out.items():
        target_dir = os.path.join(src_main, folder)
        os.makedirs(target_dir, exist_ok=True)
        template = env.get_template(template_name)
        for m in models:
            with open(os.path.join(target_dir, file_pattern.format(m["class_name"])), "w", encoding="utf-8") as f:
                f.write(template.render(e=m))

    exceptions_dir = os.path.join(src_main, "exceptions")
    os.makedirs(exceptions_dir, exist_ok=True)
    for template_name, file_name in (
        ("not_found_exception.java.j2", "NotFoundException.java"),
        ("bad_request_exception.java.j2", "BadRequestException.java"),
        ("api_exception_handler.java.j2", "ApiExceptionHandler.java"),
    ):
        with open(os.path.join(exceptions_dir, file_name), "w", encoding="utf-8") as f:
            f.write(env.get_template(template_name).render())
    return models
