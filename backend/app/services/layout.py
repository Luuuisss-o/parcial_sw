# app/services/layout.py
"""
Ubicación inicial de las clases de un diagrama importado (foto o XMI).

Antes se ponían en una grilla de 3 columnas en el orden en que llegaban, sin
mirar las relaciones: las líneas se cruzaban por todo el diagrama. Ahora se
usa un acomodo por niveles, como se dibuja un diagrama de clases a mano:

- Arriba lo "general": el padre de una herencia, la interfaz que se
  realiza, el todo de una composición/agregación, la clase referenciada por
  una asociación (en un diagrama de BD, la tabla a la que apunta la FK).
- Debajo, cada clase un nivel por debajo de las que apunta.
- Dentro de cada nivel, las clases se ordenan por el promedio de la posición
  de sus vecinas (heurística del baricentro), para cruzar menos líneas.
- Las clases sin ninguna relación van al final, en filas aparte.

Todo en celdas de la grilla del editor (16 px).
"""
from __future__ import annotations

CARD_W = 12        # ancho de una tarjeta, en celdas
COL_GAP = 8        # espacio horizontal entre tarjetas
ROW_GAP = 6        # espacio vertical entre niveles
MAX_PER_ROW = 5    # un nivel con más clases se parte en varias filas
MARGIN = 2         # separación del borde del lienzo


def estimate_rows(n_attrs: int) -> int:
    """Alto aproximado de la tarjeta en el lienzo (nombre + atributos; el
    compartimento de métodos no se muestra en las tarjetas)."""
    return max(5, int(4 + max(n_attrs, 1) * 1.25 + 0.999))


def layered_positions(names: list[str], edges: list[tuple[str, str]],
                      heights: dict[str, int]) -> dict[str, tuple[int, int]]:
    """{nombre: (x_grid, y_grid)}. `edges`: (desde, hacia), donde "hacia" es
    la clase que va más arriba (padre, interfaz, todo, referenciada)."""
    names = list(dict.fromkeys(names))  # sin repetidos, en el orden recibido
    known = set(names)
    up: dict[str, set[str]] = {n: set() for n in names}
    down: dict[str, set[str]] = {n: set() for n in names}
    for a, b in edges:
        if a in known and b in known and a != b:
            up[a].add(b)
            down[b].add(a)

    # Nivel = largo del camino más largo hacia arriba (los ciclos se cortan).
    level: dict[str, int] = {}

    def depth(n: str, stack: frozenset) -> int:
        if n in level:
            return level[n]
        parents = [p for p in up[n] if p not in stack]
        d = 0 if not parents else 1 + max(depth(p, stack | {n}) for p in parents)
        level[n] = d
        return d

    connected = [n for n in names if up[n] or down[n]]
    isolated = [n for n in names if not up[n] and not down[n]]
    for n in connected:
        depth(n, frozenset())

    layers: dict[int, list[str]] = {}
    for n in connected:
        layers.setdefault(level[n], []).append(n)

    # Orden dentro de cada nivel: baricentro de los vecinos ya ubicados,
    # bajando y después subiendo (dos pasadas alcanzan para pocas clases).
    pos: dict[str, float] = {}
    for lv in sorted(layers):
        for i, n in enumerate(layers[lv]):
            pos[n] = i

    def bary(n: str, neigh: set[str]) -> float:
        xs = [pos[m] for m in neigh if m in pos]
        return sum(xs) / len(xs) if xs else pos[n]

    for order in (sorted(layers), sorted(layers, reverse=True)):
        for lv in order:
            row = layers[lv]
            neigh = up if order[0] == min(layers) else down
            row.sort(key=lambda n: (bary(n, neigh[n]), names.index(n)))
            for i, n in enumerate(row):
                pos[n] = i

    # Filas: cada nivel (partido si es muy ancho) y al final las aisladas.
    rows: list[list[str]] = []
    for lv in sorted(layers):
        row = layers[lv]
        rows += [row[i:i + MAX_PER_ROW] for i in range(0, len(row), MAX_PER_ROW)]
    rows += [isolated[i:i + MAX_PER_ROW] for i in range(0, len(isolated), MAX_PER_ROW)]

    step = CARD_W + COL_GAP
    widest = max((len(r) for r in rows), default=1)
    out: dict[str, tuple[int, int]] = {}
    y = 0
    for row in rows:
        parents = [[out[p][0] for p in up[n] if p in out] for n in row]
        if any(parents):
            # Cada clase debajo del promedio de sus padres, sin pisarse con la
            # de al lado (se corre a la derecha lo que haga falta).
            want = [sum(px) / len(px) if px else None for px in parents]
            x_prev = None
            for i, n in enumerate(row):
                w = want[i] if want[i] is not None else (x_prev + step if x_prev is not None else 0)
                x = max(int(round(w)), x_prev + step if x_prev is not None else 0)
                out[n] = (x, y)
                x_prev = x
        else:
            # Primera fila (o clases sueltas): centrada respecto de la más ancha.
            x0 = (widest - len(row)) * step // 2
            for i, n in enumerate(row):
                out[n] = (x0 + i * step, y)
        y += max(heights.get(n, 6) for n in row) + ROW_GAP
    return {n: (x + MARGIN, y + MARGIN) for n, (x, y) in out.items()}


def anchor_sides(src: tuple[int, int], dst: tuple[int, int], src_h: int, dst_h: int) -> tuple[str, str]:
    """Lados (src_anchor, dst_anchor) para la línea entre dos clases ya
    ubicadas: si una está en otra fila, la línea sale por arriba/abajo; si
    están a la misma altura, por los costados enfrentados. Sin esto el lienzo
    usa derecha -> izquierda para todo y en un acomodo vertical las líneas
    cruzan las tarjetas."""
    (sx, sy), (dx, dy) = src, dst
    if sy >= dy + dst_h:          # el origen está debajo (hija -> padre)
        return "top", "bottom"
    if dy >= sy + src_h:          # el origen está arriba
        return "bottom", "top"
    return ("left", "right") if sx > dx else ("right", "left")
