import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import prompt_contract as pc  # noqa: E402


def test_system_prompt_se_lee_del_archivo_dart():
    p = pc.system_prompt()
    assert p.startswith("Sos un integrante más del equipo")
    assert '{"say":' in p and "por su nombre de pila" in p


def test_mensaje_de_usuario_coincide_con_la_referencia_compartida_con_dart():
    ctx = json.loads((ROOT / "fixtures" / "context_example.json").read_text(encoding="utf-8"))
    expected = (ROOT / "fixtures" / "context_example.expected.txt").read_text(encoding="utf-8")
    assert pc.build_user_message(ctx) == expected


def test_diagrama_vacio():
    assert pc.compact_diagram({}) == "(vacío)"
