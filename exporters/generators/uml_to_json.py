# exporters/generators/uml_to_json.py
"""
Convierte un UML (ya en formato dict) a un archivo JSON estándar.
"""

import json
import re
from exporters.generators.validator import validate_diagram, UMLValidationError

# Los nombres de clase del diagrama son libres (el usuario los escribe a
# mano, o vienen de una foto leida por Gemini): pueden traer espacios,
# tildes, numeros al inicio, etc. Java no acepta nada de eso en un
# identificador de clase/campo, asi que TODO nombre que llega a los
# generadores tiene que pasar por aca primero -- normalizar en un solo
# lugar temprano en el pipeline evita que cada generador (modelo,
# repository, service, controller, dto, postman) tenga que sanearlo por
# su cuenta y se termine escapando alguno.
_INVALID_CHARS_RE = re.compile(r"[^0-9a-zA-Z_]")


def _to_pascal_case(name: str) -> str:
    """'ATM Transactions' -> 'ATMTransactions', 'unidad-medida' -> 'UnidadMedida'."""
    cleaned = _INVALID_CHARS_RE.sub(" ", name).strip()
    parts = [p for p in cleaned.split(" ") if p]
    if not parts:
        return "Clase"
    pascal = "".join(p[:1].upper() + p[1:] for p in parts)
    # Java no permite que un identificador empiece con un digito.
    if pascal[0].isdigit():
        pascal = f"C{pascal}"
    return pascal


def _normalize_diagram(diagram: dict) -> dict:
    name_map = {c["name"]: _to_pascal_case(c["name"]) for c in diagram.get("classes", [])}

    for c in diagram.get("classes", []):
        c["name"] = name_map[c["name"]]

    for rel in diagram.get("relations", []):
        if rel.get("from") in name_map:
            rel["from"] = name_map[rel["from"]]
        if rel.get("to") in name_map:
            rel["to"] = name_map[rel["to"]]
        if rel.get("role_from"):
            rel["role_from"] = _to_pascal_case(rel["role_from"])[:1].lower() + _to_pascal_case(rel["role_from"])[1:]
        if rel.get("role_to"):
            rel["role_to"] = _to_pascal_case(rel["role_to"])[:1].lower() + _to_pascal_case(rel["role_to"])[1:]

    return diagram


def export_diagram_to_json(diagram_dict: dict, output_path: str) -> str:
    """
    Normaliza, valida y exporta un diagrama UML a JSON.
    - diagram_dict: diccionario con clases, atributos, métodos, relaciones
    - output_path: ruta donde guardar el JSON
    """
    # 1. Normalizar nombres a identificadores Java validos (ver arriba).
    diagram_dict = _normalize_diagram(diagram_dict)

    # 2. Validar
    validate_diagram(diagram_dict)

    # 3. Guardar en archivo JSON
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"diagram": diagram_dict}, f, indent=4, ensure_ascii=False)

    return output_path
