"""Invariantes del dataset de personalización (training/data/*.jsonl)."""
import json
import re
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import prompt_contract as pc  # noqa: E402

TOOLS = {
    "create_class": {"name"},
    "rename_class": {"class_name", "new_name"},
    "delete_class": {"class_name"},
    "add_attribute": {"class_name", "name", "type"},
    "delete_attribute": {"class_name", "attribute_name"},
    "add_method": {"class_name", "name", "return_type"},
    "delete_method": {"class_name", "method_name"},
    "create_relation": {"from_class", "to_class", "type"},
    "delete_relation": {"from_class", "to_class"},
}
TYPES = {"String", "Integer", "Double", "LocalDate", "Boolean"}
REL_TYPES = {"ASSOCIATION", "AGGREGATION", "COMPOSITION", "INHERITANCE", "DEPENDENCY"}


def rows(name):
    p = ROOT / "data" / name
    if not p.exists():
        pytest.skip("dataset no generado (correr build_dataset.py)")
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()]


@pytest.fixture(scope="module")
def all_rows():
    return rows("train.jsonl") + rows("eval.jsonl")


def test_tamano_y_split(all_rows):
    assert len(rows("train.jsonl")) > 1000 and len(rows("eval.jsonl")) > 50


def test_cada_ejemplo_respeta_el_contrato_de_la_app(all_rows):
    system = pc.system_prompt()
    for r in all_rows:
        user, assistant = r["messages"]
        assert user["role"] == "user" and assistant["role"] == "assistant"
        assert user["content"].startswith(system + "\n\n")  # mismo prompt que la app
        who = re.search(r"^Quien pregunta: (.+)$", user["content"], re.M).group(1)
        out = json.loads(assistant["content"])
        assert set(out) == {"say", "actions"}
        assert out["say"].startswith(who.split()[0] + ","), out["say"][:60]
        assert "{nombre}" not in out["say"]
        created = set(re.findall(r"^(\w+)\(", user["content"].split("Diagrama actual:\n", 1)[1], re.M))
        for a in out["actions"]:
            assert a["tool"] in TOOLS, a
            assert TOOLS[a["tool"]] <= set(a["args"]), a
            if a["tool"] == "add_attribute":
                assert a["args"]["type"] in TYPES
            if a["tool"] == "create_class":
                created.add(a["args"]["name"])
            if a["tool"] == "create_relation":
                assert a["args"]["type"] in REL_TYPES
                # solo relaciona clases que existen o que se crearon antes en la misma respuesta
                assert {a["args"]["from_class"], a["args"]["to_class"]} <= created, (a, created)


def test_mentoria_sin_acciones_y_soluciones_segun_configuracion(all_rows):
    kinds = Counter()
    for r in all_rows:
        user, out = r["messages"][0]["content"], json.loads(r["messages"][1]["content"])
        q = user.rsplit("Consulta actual de", 1)[1]
        if "armame el diagrama" in q or "diseñá el sistema" in q or "todo el modelo" in q or "construí las clases" in q:
            if "Entrega de soluciones: DESACTIVADA" in user:
                assert out["actions"] == [] and "desactivada" in out["say"]
                kinds["solucion_rechazada"] += 1
            else:
                assert len([a for a in out["actions"] if a["tool"] == "create_class"]) >= 3
                kinds["solucion_entregada"] += 1
        elif not out["actions"]:
            kinds["mentoria"] += 1
        else:
            kinds["edicion"] += 1
    assert kinds["mentoria"] >= 400 and kinds["edicion"] >= 600
    assert kinds["solucion_rechazada"] >= 30 and kinds["solucion_entregada"] >= 30


def test_hilo_individual_resuelve_referencias(all_rows):
    con_hilo = [r for r in all_rows if "Consultas previas de" in r["messages"][0]["content"]]
    assert len(con_hilo) >= 100
    for r in con_hilo:
        user, out = r["messages"][0]["content"], json.loads(r["messages"][1]["content"])
        clase_del_hilo = re.search(r"IA: \w+, creé la clase (\w+)", user).group(1)
        assert out["actions"][0]["args"]["class_name"] == clase_del_hilo  # no la del compañero
