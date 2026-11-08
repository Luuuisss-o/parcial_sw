#json_to_relations.json
"""
json_to_relations.py
Lee el JSON y genera un mapa de relaciones con anotaciones JPA sugeridas.
"""

import json
import re

# Cualquier caracter que no sea letra/digito se trata como separador de
# palabra. Necesario porque el nombre de un atributo puede venir de una
# foto leida por Gemini con puntuacion pegada (ej. "account no." como
# abreviatura de "account number"), y un "." (o cualquier otro simbolo)
# en un identificador Java ni siquiera compila.
_WORD_SPLIT_RE = re.compile(r"[^0-9a-zA-Z]+")


def to_camel(name: str) -> str:
    """Convierte nombres a camelCase: 'UnidadMedida' -> 'unidadMedida',
    'unidad_medida' -> 'unidadMedida', 'transaction id' -> 'transactionId',
    'account no.' -> 'accountNo'."""
    parts = [p for p in _WORD_SPLIT_RE.split(name) if p]
    if not parts:
        return name
    return parts[0].lower() + "".join(p.capitalize() for p in parts[1:])

def build_relations(json_path: str):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    relations_map = {}
    diagram = data["diagram"]

    for rel in diagram["relations"]:
        src = rel["from"]   # origen en el JSON
        dst = rel["to"]     # destino en el JSON
        rel_type = rel["type"]
        from_max = rel["from_max"]
        to_max = rel["to_max"]

        if src not in relations_map:
            relations_map[src] = {}
        if dst not in relations_map:
            relations_map[dst] = {}

        # ==============================
        # Herencia
        # ==============================
        if rel_type == "INHERITANCE":
            hijo = src
            padre = dst

            relations_map[hijo][padre] = {
              "type": "Extends",
              "parent": padre
            }

            relations_map[padre][hijo] = {
              "type": "Inheritance",
              "annotation": "@Inheritance(strategy = InheritanceType.JOINED)"
            }
            continue

        # ==============================
        # Composición
        # ==============================
        if rel_type == "COMPOSITION":
            padre = dst
            hijo = src

            relations_map[padre][hijo] = {
                "type": "Composition",
                "annotation": "@OneToMany(cascade = CascadeType.ALL, orphanRemoval = true)",
                "mappedBy": to_camel(padre)
            }

            relations_map[hijo][padre] = {
                "type": "Composition",
                "annotation": "@ManyToOne",
                "joinColumn": f"{to_camel(padre)}_id"
            }
            continue
        # ==============================
        # Agregación
        # ==============================
        if rel_type == "AGGREGATION":
            padre = dst
            hijo = src

            relations_map[padre][hijo] = {
                "type": "Aggregation",
                "annotation": "@OneToMany",
                "mappedBy": to_camel(padre)
            }

            relations_map[hijo][padre] = {
                "type": "Aggregation",
                "annotation": "@ManyToOne",
                "joinColumn": f"{to_camel(padre)}_id"
            }
            continue

        # ==============================
        # Dependencia
        # ==============================
        if rel_type == "DEPENDENCY":
            padre = dst   # el destino es el "proveedor" (ej: Impresora)
            hijo = src    # el origen depende del destino (ej: Factura)

            relations_map[hijo][padre] = {
                "type": "Dependency",
                "annotation": "@OneToOne",
                "joinColumn": f"{to_camel(padre)}_id"
            }
            relations_map[padre][hijo] = {
                "type": "Dependency",
                "annotation": f"@OneToOne(mappedBy = \"{to_camel(padre)}\")"
            }
            continue

        # ==============================
        # Asociación
        # ==============================
        if rel_type == "ASSOCIATION":
            if src == dst:
                # Recursivas
                if (from_max in (None, "*")) and (to_max in (None, "*")):
                    label = rel.get("label", "related")
                    relations_map[src][dst] = {
                        "type": "RecursiveAssociation",
                        "annotation": "@ManyToMany",
                        "joinTable": f"{to_camel(src)}_{to_camel(dst)}",
                        "label": label
                    }
                    relations_map[dst][src] = {
                        "type": "RecursiveAssociation",
                        "annotation": f"@ManyToMany(mappedBy = \"{label}\")",
                        "label": label + "De",
                        "mappedByTarget": label  # 👈 Campo dueño al que referencia
                    }

                elif from_max == 1 and (to_max in (None, "*")):
                    relations_map[src][dst] = {
                        "type": "RecursiveAssociation",
                        "annotation_one": "@OneToMany(mappedBy = \"parent\")",
                        "annotation_two": "@ManyToOne",
                        "joinColumn": f"{to_camel(src)}Parent_id"
                    }
                elif (from_max in (None, "*")) and to_max == 1:
                    relations_map[src][dst] = {
                        "type": "RecursiveAssociation",
                        "annotation_one": "@ManyToOne",
                        "annotation_two": "@OneToMany(mappedBy = \"child\")",
                        "joinColumn": f"{to_camel(src)}Child_id"
                    }
                else:
                    relations_map[src][dst] = {
                        "type": "RecursiveAssociation",
                        "annotation": "@OneToOne",
                        "joinColumn": f"{to_camel(src)}Ref_id"
                    }
            else:
                # Asociación normal
                if from_max == 1 and (to_max in (None, "*")):
                    relations_map[src][dst] = {
                        "type": "OneToMany",
                        "annotation": "@OneToMany"
                    }
                    relations_map[dst][src] = {
                        "type": "ManyToOne",
                        "annotation": "@ManyToOne",
                        "joinColumn": f"{to_camel(src)}_id"
                    }

                elif (from_max in (None, "*")) and to_max == 1:
                    relations_map[src][dst] = {
                        "type": "ManyToOne",
                        "annotation": "@ManyToOne",
                        "joinColumn": f"{to_camel(dst)}_id"
                    }
                    relations_map[dst][src] = {
                        "type": "OneToMany",
                        "annotation": f"@OneToMany(mappedBy = \"{to_camel(dst)}\")"
                    }


                elif from_max == 1 and to_max == 1:
                    relations_map[src][dst] = {
                        "type": "OneToOne",
                        "annotation": "@OneToOne",
                        "joinColumn": f"{to_camel(dst)}_id",
                        "role_name": rel.get("role_to") or to_camel(dst)
                    }
                    relations_map[dst][src] = {
                        "type": "OneToOne",
                        "annotation": f"@OneToOne(mappedBy = \"{rel.get('role_to') or to_camel(dst)}\")",
                        "role_name": rel.get("role_from") or to_camel(src)
                    }
                elif (from_max in (None, "*")) and (to_max in (None, "*")):
                    owner_role_name = rel.get("role_to") or to_camel(dst) + "s"
                    relations_map[src][dst] = {
                        "type": "ManyToMany",
                        "annotation": "@ManyToMany",
                        "joinTable": f"{to_camel(src)}_{to_camel(dst)}",
                        "joinColumns": f"{to_camel(src)}_id",
                       "inverseJoinColumns": f"{to_camel(dst)}_id",
                        "role_name": rel.get("role_to") or to_camel(dst) + "s"
                    }
                    relations_map[dst][src] = {
                        "type": "ManyToMany",
                        # 👇 mappedBy debe referirse al atributo generado en la otra clase
                        "annotation": "@ManyToMany",

                        "role_name": rel.get("role_from") or to_camel(src) + "s",
                        "mappedByTarget": owner_role_name
                              }


    return relations_map

if __name__ == "__main__":
    relations = build_relations("../json/diagram.json")
    print(json.dumps(relations, indent=4))
