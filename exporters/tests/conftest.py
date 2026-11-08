"""
Fixtures compartidas para los tests de exporters/.

El fixture principal es un diagrama JSON ya en el formato final que produce
uml_to_json.export_diagram_to_json (normalizado y validado) -- los tests de
los generadores individuales no necesitan pasar por la normalizacion cada
vez, les alcanza con un archivo fijo y conocido.
"""
import json
import shutil
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def diagram_tienda_path(tmp_path) -> str:
    """Copia el diagrama fijo (Cliente, Producto, Pedido) a un archivo
    temporal y devuelve su ruta. Se copia (no se usa el original directo)
    para que cada test tenga su propia copia aislada, igual que en
    produccion cada export corre sobre su propio JSON en un tmpdir."""
    src = FIXTURES_DIR / "diagram_tienda.json"
    dst = tmp_path / "diagram_tienda.json"
    shutil.copy(src, dst)
    return str(dst)


@pytest.fixture
def diagram_tienda_dict() -> dict:
    """El mismo diagrama, ya cargado como dict, para tests que no necesitan
    tocar el filesystem."""
    with open(FIXTURES_DIR / "diagram_tienda.json", "r", encoding="utf-8") as f:
        return json.load(f)
