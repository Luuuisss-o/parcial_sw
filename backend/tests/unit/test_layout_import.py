"""
Acomodo inicial de las clases importadas (foto o XMI): por niveles según las
relaciones, en vez de una grilla en el orden de llegada.
"""
from app.services.layout import CARD_W, estimate_rows, layered_positions


def _sin_superposicion(pos, heights):
    cajas = [(x, y, x + CARD_W, y + heights.get(n, 6)) for n, (x, y) in pos.items()]
    for i, a in enumerate(cajas):
        for b in cajas[i + 1:]:
            assert a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1], (a, b)


def test_padre_arriba_e_hijos_debajo():
    edges = [("Persiana", "Ventana"), ("Ventana", "Casa"), ("Calefactor", "Casa"), ("Puerta", "Casa")]
    names = ["Persiana", "Ventana", "Calefactor", "Casa", "Puerta", "Suelta"]
    pos = layered_positions(names, edges, {})
    y = {n: p[1] for n, p in pos.items()}
    assert y["Casa"] < y["Ventana"] == y["Calefactor"] == y["Puerta"] < y["Persiana"]
    assert y["Suelta"] > y["Persiana"]                  # las clases sin relaciones, al final
    assert pos["Persiana"][0] == pos["Ventana"][0]      # el hijo, debajo de su padre
    _sin_superposicion(pos, {})


def test_modelo_de_bd_tabla_referenciada_arriba():
    edges = [("pedido", "cliente"), ("detalle_pedido", "pedido"), ("detalle_pedido", "producto")]
    pos = layered_positions(["cliente", "pedido", "detalle_pedido", "producto"], edges, {})
    assert pos["cliente"][1] == pos["producto"][1] < pos["pedido"][1] < pos["detalle_pedido"][1]


def test_ciclos_y_nivel_ancho_no_se_superponen():
    names = [f"C{i}" for i in range(12)]
    edges = [(f"C{i}", "C0") for i in range(1, 12)] + [("C0", "C1")]  # ciclo C0 <-> C1
    heights = {n: estimate_rows(i % 5) for i, n in enumerate(names)}
    pos = layered_positions(names, edges, heights)
    assert set(pos) == set(names)
    _sin_superposicion(pos, heights)


def test_alto_estimado_crece_con_atributos():
    assert estimate_rows(0) == estimate_rows(1) >= 5
    assert estimate_rows(10) > estimate_rows(2)


def test_lados_de_la_linea_segun_el_acomodo():
    from app.services.layout import anchor_sides
    assert anchor_sides((2, 20), (2, 2), 6, 6) == ("top", "bottom")     # hija debajo del padre
    assert anchor_sides((2, 2), (2, 20), 6, 6) == ("bottom", "top")
    assert anchor_sides((22, 2), (2, 2), 6, 6) == ("left", "right")     # misma fila
    assert anchor_sides((2, 2), (22, 4), 6, 6) == ("right", "left")


def test_margen_del_lienzo():
    pos = layered_positions(["A"], [], {})
    assert pos["A"][0] > 0 and pos["A"][1] > 0
