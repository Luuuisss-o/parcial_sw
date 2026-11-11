# app/schemas/uml_notation.py
#
# Tipos y validaciones de la notación UML 2.5 del diagrama de clases,
# compartidos por los esquemas de clase, atributo, método y relación.
import re
from typing import Literal, Optional

ClassKind = Literal["class", "abstract", "interface", "enumeration"]
Visibility = Literal["+", "-", "#", "~"]

# Multiplicidad UML: "1", "*", "0..1", "1..*", "2..5"
_MULT_RE = re.compile(r"^(\*|\d+)(\.\.(\*|\d+))?$")


def normalize_multiplicity(v: Optional[str]) -> Optional[str]:
    """Acepta "0..*", "[0..*]" o "" (sin multiplicidad). Valida que el
    límite inferior no supere al superior."""
    if v is None:
        return None
    v = str(v).strip().removeprefix("[").removesuffix("]").replace(" ", "")
    if not v:
        return None
    m = _MULT_RE.match(v)
    if not m:
        raise ValueError("multiplicidad inválida: usá 1, *, 0..1, 1..* o n..m")
    low, high = m.group(1), m.group(3)
    if high is not None:
        if low == "*":
            raise ValueError("multiplicidad inválida: el límite inferior no puede ser *")
        if high != "*" and int(high) < int(low):
            raise ValueError("multiplicidad inválida: el límite superior es menor que el inferior")
    return v


def clean_optional_text(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    v = str(v).strip()
    return v or None
