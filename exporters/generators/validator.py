# exporters/generators/validator.py
"""
validator.py
Valida que el diagrama UML tenga consistencia antes de exportarlo.
"""

# Tipos de relacion reconocidos por json_to_relations.build_relations. Un
# tipo fuera de este set hoy pasa silencioso: build_relations no encuentra
# ninguna rama que matchee, la relacion simplemente no se traduce a
# ninguna anotacion JPA y el generador de entidades actua como si esa
# relacion no existiera -- sin ningun aviso de que el diagrama tenia un
# dato invalido. Mejor rechazarlo en la validacion, antes de generar nada.
_VALID_RELATION_TYPES = {"ASSOCIATION", "AGGREGATION", "COMPOSITION", "INHERITANCE", "DEPENDENCY"}


class UMLValidationError(Exception):
    """Error lanzado cuando el UML no cumple las reglas mínimas."""
    pass


def _is_valid_multiplicity_max(value) -> bool:
    """json_to_relations.build_relations solo distingue entre max==1 y
    max en (None, "*") -- cualquier otro valor (ej. un entero != 1, o un
    string que no sea "*") cae en la rama "else" de ASSOCIATION normal sin
    aviso, produciendo una relacion OneToOne donde en realidad el usuario
    quiso decir otra cosa."""
    return value is None or value == 1 or value == "*"


def validate_diagram(diagram: dict) -> None:
    """
    Valida un diagrama UML representado como diccionario.
    Espera las claves: 'id', 'title', 'classes', 'relations'.

    Reglas básicas:
    - Debe tener al menos 1 clase.
    - Cada clase debe tener un nombre único.
    - Cada atributo debe tener nombre y tipo.
    - Las relaciones deben apuntar a clases existentes.
    """

    if "classes" not in diagram or not diagram["classes"]:
        raise UMLValidationError("El diagrama debe tener al menos una clase.")

    # Validar nombres únicos
    nombres = [c["name"] for c in diagram["classes"]]
    if len(nombres) != len(set(nombres)):
        raise UMLValidationError("Existen clases con nombres duplicados.")

    # Validar atributos
    for clase in diagram["classes"]:
        for attr in clase.get("attributes", []):
            if not attr.get("name") or not attr.get("type"):
                raise UMLValidationError(
                    f"Atributo inválido en clase {clase['name']} (faltan nombre o tipo)."
                )

    # Validar relaciones
    class_names = {c["name"] for c in diagram["classes"]}
    for rel in diagram.get("relations", []):
        if rel["from"] not in class_names:
            raise UMLValidationError(f"Relación inválida: clase origen '{rel['from']}' no existe.")
        if rel["to"] not in class_names:
            raise UMLValidationError(f"Relación inválida: clase destino '{rel['to']}' no existe.")

        rel_type = rel.get("type")
        if rel_type not in _VALID_RELATION_TYPES:
            raise UMLValidationError(
                f"Relación inválida entre '{rel['from']}' y '{rel['to']}': "
                f"tipo '{rel_type}' desconocido (válidos: {', '.join(sorted(_VALID_RELATION_TYPES))})."
            )

        for side, value in (("origen", rel.get("from_max")), ("destino", rel.get("to_max"))):
            if not _is_valid_multiplicity_max(value):
                raise UMLValidationError(
                    f"Relación inválida entre '{rel['from']}' y '{rel['to']}': "
                    f"multiplicidad máxima de {side} '{value}' no es 1, \"*\" ni vacía."
                )

    # Si todo pasó:
    return None
