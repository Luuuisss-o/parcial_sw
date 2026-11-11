// src/components/canvas/utils/layout.js
//
// Separar clases superpuestas. Un diagrama que no armó una persona a mano
// (importado desde una foto o un XMI, o creado por la IA) ubica las clases
// en una grilla fija, pero cada tarjeta crece después según sus atributos y
// métodos: las de una fila terminan tapando a las de la fila de abajo.
//
// Criterio: tocar lo menos posible. Se recorren las clases de arriba hacia
// abajo (y de izquierda a derecha); una clase que no choca con ninguna ya
// ubicada se queda donde está, y una que choca baja justo debajo de la que
// la tapa, en su misma columna. Así el diagrama conserva la disposición que
// tenía (columnas, orden) y solo se abre espacio donde hacía falta.

/** Separación mínima entre tarjetas, en celdas de la grilla. */
export const LAYOUT_GAP = 2;

function overlaps(a, b, gap) {
  return (
    a.x < b.x + b.w + gap &&
    b.x < a.x + a.w + gap &&
    a.y < b.y + b.h + gap &&
    b.y < a.y + a.h + gap
  );
}

/**
 * @param {{id: string, x: number, y: number, w: number, h: number}[]} rects
 *   posición y tamaño de cada clase, en celdas.
 * @returns {Map<string, {x: number, y: number}>} solo las clases que hay que
 *   mover, con su nueva posición. Vacío si nada se superpone.
 */
export function resolveOverlaps(rects, gap = LAYOUT_GAP) {
  const ordered = [...rects].sort((a, b) => a.y - b.y || a.x - b.x);
  const placed = [];
  const moves = new Map();

  for (const r of ordered) {
    const cur = { ...r };
    // Baja hasta que no choque con ninguna ya ubicada (siempre termina:
    // cada vuelta queda por debajo de al menos una de ellas).
    for (;;) {
      const hits = placed.filter((p) => overlaps(cur, p, gap));
      if (hits.length === 0) break;
      cur.y = Math.max(...hits.map((p) => p.y + p.h + gap));
    }
    if (cur.y !== r.y) moves.set(r.id, { x: cur.x, y: cur.y });
    placed.push(cur);
  }
  return moves;
}

/** ¿Hay al menos un par de clases superpuestas (sin contar la separación)? */
export function hasOverlaps(rects) {
  for (let i = 0; i < rects.length; i++) {
    for (let j = i + 1; j < rects.length; j++) {
      if (overlaps(rects[i], rects[j], 0)) return true;
    }
  }
  return false;
}
