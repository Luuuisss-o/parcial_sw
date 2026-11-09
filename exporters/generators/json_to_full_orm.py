"""
json_to_full_orm.py
Convierte un diagrama UML (JSON) a entidades Java con JPA: atributos y
relaciones (usando json_to_relations) en un solo generador.
"""

import copy, os, json, re
from exporters.generators.json_to_relations import build_relations, to_camel
from exporters.generators.type_mapping import map_type

_DECL_RE = re.compile(r"^\s*private (List<(\w+)>|(\w+)) (\w+);$")


def _relation_fields(rel_lines: list[str]) -> list[dict]:
    """Campos de relacion declarados en `rel_lines` (la seccion de relaciones
    de la entidad): nombre, clase destino, si es lista y si es el lado DUENO
    (el que persiste la FK / la tabla intermedia; el lado `mappedBy` es solo
    lectura para JPA)."""
    fields, annotations = [], []
    for line in rel_lines:
        m = _DECL_RE.match(line)
        if not m:
            if line.strip():
                annotations.append(line)
            continue
        fields.append({
            "name": m.group(4),
            "target": m.group(2) or m.group(3),
            "is_list": m.group(2) is not None,
            "owner": not any("mappedBy" in a for a in annotations),
            "java_type": m.group(1),
            "cap": m.group(4)[0].upper() + m.group(4)[1:],
        })
        annotations = []
    return fields


# ========================
# Generador de entidad con relaciones
# ========================
def generate_entity(class_def: dict, relations_map: dict):
    return build_entity(class_def, relations_map)[0]


def build_entity(class_def: dict, relations_map: dict):
    """Devuelve (codigo Java de la entidad, campos de relacion)."""
    class_def = copy.deepcopy(class_def)  # se le inserta "id": no tocar el original
    class_name = class_def["name"]
    attributes = class_def.get("attributes", [])

    # Detectar si es clase hija (Extends)
    is_child = any(
        rel["type"] == "Extends"
        for rels in relations_map.get(class_name, {}).values()
        for rel in [rels]
    )

    # 🔹 Solo el padre lleva id, los hijos heredan
    if not is_child:
        has_id = any(attr["name"].lower() == "id" for attr in attributes)
        if not has_id:
            attributes.insert(0, {"name": "id", "type": "long", "required": True})

    lines = []
    lines.append("package com.test.models;")
    lines.append("")
    lines.append("import jakarta.persistence.*;")
    lines.append("import com.fasterxml.jackson.annotation.JsonIgnore;")
    lines.append("import java.time.*;")
    lines.append("import java.util.*;")
    lines.append("")
    lines.append("@Entity")

    # ========================
    # Herencia
    # ========================
    extends_clause = ""
    inheritance_added = False
    if class_name in relations_map:
        for target, rel in relations_map[class_name].items():
            if rel["type"] == "Inheritance" and not inheritance_added:
                lines.append(rel["annotation"])
                inheritance_added = True
            elif rel["type"] == "Extends":
                extends_clause = f" extends {rel['parent']}"

    lines.append(f"public class {class_name}{extends_clause} " + "{")
    lines.append("")

    # ========================
    # Atributos normales
    # ========================
    for attr in attributes:
        attr_name = to_camel(attr["name"])
        # attr_type = map_type(attr["type"])

        if attr_name.lower() == "id" and not is_child:
            lines.append("    @Id")
            lines.append("    @GeneratedValue(strategy = GenerationType.IDENTITY)")
            attr_type = "Long"   # 👈 Forzamos que siempre sea Long
        else:
            attr_type = map_type(attr["type"])

        lines.append(f"    private {attr_type} {attr_name};")
        lines.append("")

    # ========================
    # Relaciones JPA
    # ========================
    rel_start = len(lines)
    if class_name in relations_map:
        # 👇 Procesar primero el lado dueño (joinTable), luego mappedBy
        for target, rel in sorted(
            relations_map[class_name].items(),
            key=lambda kv: 0 if "joinTable" in kv[1] else 1
        ):
            rel_type = rel["type"]
            if target.lower() == "id":
                continue
            if rel_type in ("Inheritance", "Extends"):
                continue

            # --- Recursivas ---
            if rel_type == "RecursiveAssociation":
                if "annotation_one" in rel and "annotation_two" in rel:
                    lines.append(f"    {rel['annotation_one']}")
                    lines.append(f"    private List<{class_name}> children;")
                    lines.append("")
                    lines.append(f"    {rel['annotation_two']}")
                    lines.append(f"    @JoinColumn(name = \"{rel['joinColumn']}\")")
                    lines.append(f"    private {class_name} parent;")
                # elif "annotation" in rel and rel["annotation"].startswith("@ManyToMany"):
                #     role_name = rel.get("label") or "related"
                #     if "joinTable" in rel:  # lado dueño
                #         lines.append(f"    {rel['annotation']}")
                #         lines.append(f"    @JoinTable(name = \"{rel['joinTable']}\")")
                #     elif "mappedByTarget" in rel:  # lado inverso
                #         lines.append(f"    @ManyToMany(mappedBy = \"{rel['mappedByTarget']}\")")
                #     else:
                #         lines.append(f"    {rel['annotation']}")
                #     lines.append(f"    private List<{class_name}> {role_name};")
                # else:
                #     role_name = rel.get("label") or "reference"
                #     lines.append(f"    {rel['annotation']}")
                #     lines.append(f"    @JoinColumn(name = \"{rel['joinColumn']}\")")
                #     lines.append(f"    private {class_name} {role_name};")
                elif "annotation" in rel and rel["annotation"].startswith("@ManyToMany"):
                    label = rel.get("label") or "related"

    # 👉 Lado dueño
                    lines.append(f"    @ManyToMany")
                    lines.append(f"    @JoinTable(")
                    lines.append(f"        name = \"{to_camel(class_name)}_{to_camel(class_name)}\",")
                    lines.append(f"        joinColumns = @JoinColumn(name = \"{to_camel(class_name)}_id\"),")
                    lines.append(f"        inverseJoinColumns = @JoinColumn(name = \"{label}_id\")")
                    lines.append(f"    )")
                    lines.append(f"    private List<{class_name}> {label};")
                    lines.append("")

    # 👉 Lado inverso
                    lines.append(f"    @ManyToMany(mappedBy = \"{label}\")")
                    lines.append(f"    private List<{class_name}> {label}De;")

            # --- Composición ---
            elif rel_type == "Composition":
                if "mappedBy" in rel:
                    role_name = rel.get("label") or to_camel(target) + "s"
                    mapped_by = rel["mappedBy"]

                    if "(" in rel['annotation']:
                        base = rel['annotation'].rstrip(")")
                        lines.append(f"    {base}, mappedBy = \"{mapped_by}\")")
                    else:
                        lines.append(f"    {rel['annotation']}(mappedBy = \"{mapped_by}\")")

                    lines.append(f"    private List<{target}> {role_name};")
                else:
                    role_name = rel.get("label") or to_camel(target)
                    lines.append(f"    {rel['annotation']}")
                    lines.append(f"    @JoinColumn(name = \"{rel['joinColumn']}\")")
                    lines.append(f"    private {target} {role_name};")

            # --- Agregación ---
            elif rel_type == "Aggregation":
                if "mappedBy" in rel:
                    role_name = rel.get("label") or to_camel(target) + "s"
                    mapped_by = rel["mappedBy"]
                    lines.append(f"    {rel['annotation']}(mappedBy = \"{mapped_by}\")")
                    lines.append(f"    private List<{target}> {role_name};")
                else:
                    role_name = rel.get("label") or to_camel(target)
                    lines.append(f"    {rel['annotation']}")
                    lines.append(f"    @JoinColumn(name = \"{rel['joinColumn']}\")")
                    lines.append(f"    private {target} {role_name};")


            # --- Dependencia ---
            elif rel_type == "Dependency":
                role_name = rel.get("label") or to_camel(target)
            
                if "joinColumn" in rel:  # lado inverso
                    lines.append(f"    {rel['annotation']}")
                    lines.append(f"    @JoinColumn(name = \"{rel['joinColumn']}\")")
                    lines.append(f"    private {target} {role_name};")
                else:  # lado dueño
                    lines.append(f"    {rel['annotation']}")
                    # lines.append(f"    @JoinColumn(name = \"{rel['joinColumn']}\")")
                    lines.append(f"    private {target} {role_name};")

            # --- Relaciones normales ---
            elif rel_type == "OneToMany":
                role_name = rel.get("label") or to_camel(target) + "s"
                mapped_by = rel.get("mappedBy") or to_camel(class_name)

                if "mappedBy" in rel['annotation']:
                    # La relacion dibujada "muchos -> uno" ya trae su mappedBy
                    # (json_to_relations); agregarle otro producia
                    # @OneToMany(mappedBy = "x", mappedBy = "x") y el proyecto
                    # generado no compilaba.
                    lines.append(f"    {rel['annotation']}")
                elif "(" in rel['annotation']:
                    base = rel['annotation'].rstrip(")")
                    lines.append(f"    {base}, mappedBy = \"{mapped_by}\")")
                else:
                    lines.append(f"    {rel['annotation']}(mappedBy = \"{mapped_by}\")")

                lines.append(f"    private List<{target}> {role_name};")

            elif rel_type == "ManyToOne":
                role_name = rel.get("label") or to_camel(target)
                col = rel.get("joinColumn", f"{to_camel(target)}_id")
                lines.append(f"    {rel['annotation']}")
                lines.append(f"    @JoinColumn(name = \"{col}\")")
              
                lines.append(f"    private {target} {role_name};")

            elif rel_type == "ManyToMany":
                role_name = rel.get("role_name") or to_camel(target) + "s"

                if "joinTable" in rel:  # 👉 lado dueño
                    lines.append("    @ManyToMany")
                    lines.append("    @JoinTable(")
                    lines.append(f"        name = \"{rel['joinTable']}\",")
                    lines.append(f"        joinColumns = @JoinColumn(name = \"{rel.get('joinColumns', to_camel(class_name) + '_id') }\"),")
                    lines.append(f"        inverseJoinColumns = @JoinColumn(name = \"{rel.get('inverseJoinColumns', to_camel(target) + '_id') }\")")
                    lines.append("    )")
                    lines.append(f"    private List<{target}> {role_name};")

                elif rel.get("mappedByTarget"):  # 👉 lado inverso
                    lines.append(f"    @ManyToMany(mappedBy = \"{rel['mappedByTarget']}\")")
                    lines.append(f"    private List<{target}> {role_name};")


            elif rel_type == "OneToOne":
                role_name = rel.get("label") or to_camel(target)
            
                if "mappedBy" in rel["annotation"]:
                    # Lado inverso (NO debe tener JoinColumn)
                    lines.append(f"    {rel['annotation']}")
                    lines.append(f"    private {target} {rel.get('role_name') or to_camel(target)};")
                else:
                    # Lado dueño (lleva JoinColumn)
                    col = rel.get("joinColumn", f"{to_camel(target)}_id")
                    lines.append(f"    {rel['annotation']}")
                    lines.append(f"    @JoinColumn(name = \"{col}\")")
                    lines.append(f"    private {target} {rel.get('role_name') or to_camel(target)};")


            lines.append("")

    rel_fields = _relation_fields(lines[rel_start:])

    # ========================
    # Getters y Setters
    # ========================
    # Relaciones: antes no tenian getters/setters, asi que no se podian leer
    # ni asignar (Pedido.cliente quedaba siempre en null). @JsonIgnore: la API
    # REST las expone como ids en el DTO; serializar la entidad con sus
    # relaciones bidireccionales entraria en recursion infinita.
    for rf in rel_fields:
        lines.append("    @JsonIgnore")
        lines.append(f"    public {rf['java_type']} get{rf['cap']}() " + "{")
        lines.append(f"        return {rf['name']};")
        lines.append("    }")
        lines.append("")
        lines.append(f"    public void set{rf['cap']}({rf['java_type']} {rf['name']}) " + "{")
        lines.append(f"        this.{rf['name']} = {rf['name']};")
        lines.append("    }")
        lines.append("")

    for attr in attributes:
        attr_name = to_camel(attr["name"])
        if attr["name"].lower() == "id":
            attr_type = "Long"   # 👈 Forzamos siempre Long para id
        else:
            attr_type = map_type(attr["type"])
        # attr_type = map_type(attr["type"])
        method_name = attr_name[0].upper() + attr_name[1:]

        lines.append(f"    public {attr_type} get{method_name}() " + "{")
        lines.append(f"        return {attr_name};")
        lines.append("    }")
        lines.append("")
        lines.append(f"    public void set{method_name}({attr_type} {attr_name}) " + "{")
        lines.append(f"        this.{attr_name} = {attr_name};")
        lines.append("    }")
        lines.append("")

    lines.append("}")
    return "\n".join(lines), rel_fields


# ========================
# Función principal
# ========================
def generate_from_json(json_path: str, output_dir=None):
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(__file__), "..", "generated", "models")
        os.makedirs(output_dir, exist_ok=True)

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    diagram = data["diagram"]
    relations_map = build_relations(json_path)

    for c in diagram["classes"]:
        code = generate_entity(c, relations_map)
        file_path = os.path.join(output_dir, f"{c['name']}.java")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(code)
        print(f"Generada entidad con relaciones: {file_path}")
