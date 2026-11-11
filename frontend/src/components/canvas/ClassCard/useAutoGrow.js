import { useCallback, useEffect, useRef } from "react";

export default function useAutoGrow({
  enabled,
  headerRef,
  bodyRef,
  CELL,
  minH,
  maxH,
  size,
  setSize,
  onResizeEnd,
  clsId,
  // Cambia cuando cambia lo que muestra la tarjeta (atributos/métodos): sin
  // esto el alto se calculaba antes de que cargaran y la tarjeta quedaba
  // cortada hasta que algo más la redibujara (un lector nunca la toca).
  contentKey = "",
}) {
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const debouncedPersistRef = useRef(null);

  const persistResizeDebounced = useCallback((newH) => {
    if (debouncedPersistRef.current) clearTimeout(debouncedPersistRef.current);
    debouncedPersistRef.current = setTimeout(() => {
      // `undoable: false` porque este alto lo calcula la tarjeta sola cuando
      // le cambia el contenido: el usuario no lo pidió, y apilarlo haría que
      // su primer Ctrl+Z deshaga un redimensionado que nunca hizo.
      onResizeEnd?.(clsId, { w_grid: size.w, h_grid: newH }, { undoable: false });
    }, 250);
  }, [onResizeEnd, clsId, size.w]);

  useEffect(() => {
    if (!enabled) return;
    const headerH = headerRef.current?.offsetHeight ?? 0;
    const bodyH = bodyRef.current?.scrollHeight ?? 0;
    const totalPx = headerH + bodyH + 16;
    const neededRows = clamp(Math.ceil(totalPx / CELL), minH, maxH);
    // Solo crece para que el contenido no se corte; nunca achica lo que el
    // usuario agrandó a mano (por ejemplo, redimensionando desde el borde
    // superior con menos atributos de los que entrarían en ese alto).
    if (neededRows > size.h) {
      setSize((s) => ({ ...s, h: neededRows }));
      persistResizeDebounced(neededRows);
    }
  }, [enabled, headerRef, bodyRef, CELL, minH, maxH, size.h, setSize, persistResizeDebounced, contentKey]);
}
