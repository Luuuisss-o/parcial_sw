import { useCallback, useEffect, useRef, useState } from "react";

export default function useDragResize({ cls, minH, maxH, CELL, onDragEnd, onResizeEnd }) {
  const [pos, setPos] = useState({ x: cls.x_grid ?? 0, y: cls.y_grid ?? 0 });
  const [size, setSize] = useState({ w: cls.w_grid ?? 12, h: cls.h_grid ?? 6 });

  const [dragging, setDragging] = useState(false);
  const [resizing, setResizing] = useState(false);
  const start = useRef({ x: 0, y: 0, px: 0, py: 0, w: 0, h: 0 });

  // pin + hover (sin cambios de lógica)
  const [pinned, setPinned] = useState(false);
  const [hover, setHover] = useState(false);

  useEffect(() => { setPos({ x: cls.x_grid ?? 0, y: cls.y_grid ?? 0 }); }, [cls.x_grid, cls.y_grid]);
  useEffect(() => { setSize({ w: cls.w_grid ?? 12, h: cls.h_grid ?? 6 }); }, [cls.w_grid, cls.h_grid]);

  const pxToGrid = (px) => Math.max(0, Math.round(px / CELL));
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const clampSize = (v, min = 3) => Math.max(min, v);

  const onHeaderMouseDown = useCallback((e) => {
    if (e.button !== 0) return;
    setDragging(true);
    start.current = { x: e.clientX, y: e.clientY, px: pos.x, py: pos.y, w: size.w, h: size.h };
    e.stopPropagation();
    e.preventDefault();
  }, [pos, size]);

  const resizeDir = useRef("se");

  /** dir: combinación de n/s (vertical) y e/w (horizontal), ej. "se", "n", "w". */
  const onHandleMouseDown = useCallback((e, dir = "se") => {
    if (e.button !== 0) return;
    resizeDir.current = dir;
    setResizing(true);
    start.current = { x: e.clientX, y: e.clientY, px: pos.x, py: pos.y, w: size.w, h: size.h };
    e.stopPropagation();
    e.preventDefault();
  }, [pos, size]);

  useEffect(() => {
    const onMove = (e) => {
      if (dragging) {
        const dx = e.clientX - start.current.x;
        const dy = e.clientY - start.current.y;
        const gx = pxToGrid(start.current.px * CELL + dx);
        const gy = pxToGrid(start.current.py * CELL + dy);
        setPos({ x: gx, y: gy });
      } else if (resizing) {
        const dx = e.clientX - start.current.x;
        const dy = e.clientY - start.current.y;
        const dir = resizeDir.current;
        const { px, py, w: w0, h: h0 } = start.current;

        let gw = w0, gh = h0, gx = px, gy = py;

        if (dir.includes("e")) {
          gw = clampSize(pxToGrid(w0 * CELL + dx));
        } else if (dir.includes("w")) {
          const rightEdge = px + w0;
          const newX = pxToGrid(px * CELL + dx);
          gx = Math.min(newX, rightEdge - 3);
          gw = rightEdge - gx;
        }

        if (dir.includes("s")) {
          gh = clamp(clampSize(pxToGrid(h0 * CELL + dy)), minH, maxH);
        } else if (dir.includes("n")) {
          const bottomEdge = py + h0;
          const newY = pxToGrid(py * CELL + dy);
          gy = Math.min(newY, bottomEdge - minH);
          gh = clamp(bottomEdge - gy, minH, maxH);
        }

        setSize({ w: gw, h: gh });
        if (dir.includes("w") || dir.includes("n")) setPos({ x: gx, y: gy });
      }
      if (dragging || resizing) {
        // Avisa a ConnectionLayer que recalcule las líneas: su posición sale
        // del DOM (getBoundingClientRect), no de este estado local, así que
        // sin este aviso la relación se quedaba fija hasta soltar el mouse.
        window.dispatchEvent(new CustomEvent("diagram:geometry-change"));
      }
    };
    const onUp = () => {
      if (dragging) {
        setDragging(false);
        onDragEnd?.(cls.id, { x_grid: pos.x, y_grid: pos.y });
      } else if (resizing) {
        setResizing(false);
        onResizeEnd?.(cls.id, { w_grid: size.w, h_grid: size.h, x_grid: pos.x, y_grid: pos.y });
      }
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [dragging, resizing, pos, size, onDragEnd, onResizeEnd, cls?.id, CELL, minH, maxH]);

  return {
    pos, size, setSize,
    dragging,
    onHeaderMouseDown,
    onHandleMouseDown,
    pinned, setPinned,
    hover, setHover,
  };
}
