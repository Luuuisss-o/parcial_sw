"""
Tests de exporters/generators/validator.py, con foco en las validaciones
agregadas para relaciones (tipo y multiplicidad) que antes pasaban
silenciosas y podian generar Java incorrecto sin ningun aviso.
"""
import pytest

from exporters.generators.validator import UMLValidationError, validate_diagram


def _diagram(relations):
    return {
        "classes": [
            {"name": "A", "attributes": [{"name": "x", "type": "string"}]},
            {"name": "B", "attributes": [{"name": "y", "type": "string"}]},
        ],
        "relations": relations,
    }


def test_valid_diagram_passes():
    diagram = _diagram([{"from": "A", "to": "B", "type": "ASSOCIATION", "from_max": 1, "to_max": "*"}])
    validate_diagram(diagram)  # no debe lanzar


def test_rejects_unknown_relation_type():
    diagram = _diagram([{"from": "A", "to": "B", "type": "FRIENDSHIP", "from_max": 1, "to_max": 1}])
    with pytest.raises(UMLValidationError, match="tipo 'FRIENDSHIP' desconocido"):
        validate_diagram(diagram)


def test_rejects_missing_relation_type():
    diagram = _diagram([{"from": "A", "to": "B", "type": None, "from_max": 1, "to_max": 1}])
    with pytest.raises(UMLValidationError):
        validate_diagram(diagram)


@pytest.mark.parametrize("invalid_max", [2, 3, "many", "0..5"])
def test_rejects_invalid_multiplicity_max(invalid_max):
    diagram = _diagram([{"from": "A", "to": "B", "type": "ASSOCIATION", "from_max": invalid_max, "to_max": 1}])
    with pytest.raises(UMLValidationError, match="multiplicidad máxima"):
        validate_diagram(diagram)


@pytest.mark.parametrize("valid_max", [1, "*", None])
def test_accepts_valid_multiplicity_max_values(valid_max):
    diagram = _diagram([{"from": "A", "to": "B", "type": "ASSOCIATION", "from_max": valid_max, "to_max": 1}])
    validate_diagram(diagram)  # no debe lanzar


def test_existing_class_and_attribute_rules_still_enforced():
    """No romper las validaciones que ya existian antes de agregar las
    nuevas reglas de relacion."""
    with pytest.raises(UMLValidationError, match="al menos una clase"):
        validate_diagram({"classes": [], "relations": []})

    with pytest.raises(UMLValidationError, match="nombres duplicados"):
        validate_diagram({
            "classes": [{"name": "A", "attributes": []}, {"name": "A", "attributes": []}],
            "relations": [],
        })

    with pytest.raises(UMLValidationError, match="clase origen"):
        validate_diagram(_diagram([{"from": "Z", "to": "B", "type": "ASSOCIATION", "from_max": 1, "to_max": 1}]))
