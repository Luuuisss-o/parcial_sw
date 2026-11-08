 
import React, { useCallback, useEffect, useRef, useState } from "react";

export const SHEET = { CELL: 16 };

export default function Sheet({ children, onCanvasClick, onEmptyClick, onCameraChange, onCursorMove, remoteCursors = [] }) {
  const { CELL } = SHEET;
  const ref = useRef(null);
  const [cam, setCam] = useState(() => ({ x: 0, y: 0, z: 1 }));
  const panning = useRef(false);
  const last = useRef({ x: 0, y: 0 });

  const onWheel = useCallback((e) => {
    e.preventDefault();
    const delta = Math.sign(e.deltaY) * 0.1;
    setCam((c) => {
      const z = Math.min(1.5, Math.max(0.5, c.z - delta)); // clamp
      return { ...c, z };
    });
  }, []);

  const moved = useRef(false);

  const onMouseDown = useCallback((e) => {
    // Botón central, Ctrl+izquierdo, o izquierdo sobre espacio vacío (no
    // sobre una clase u otro elemento interactivo) -- igual que draw.io:
    // mantener click en la pizarra y arrastrar mueve la vista.
    const onEmptySpace = e.target === e.currentTarget || e.target === ref.current?.firstElementChild;
    if (e.button !== 1 && !(e.button === 0 && (e.ctrlKey || onEmptySpace))) return;
    panning.current = true;
    moved.current = false;
    last.current = { x: e.clientX, y: e.clientY };
  }, []);

  const onMouseMove = useCallback((e) => {
    if (!panning.current) return;
    const dx = e.clientX - last.current.x;
    const dy = e.clientY - last.current.y;
    if (Math.abs(dx) > 2 || Math.abs(dy) > 2) moved.current = true;
    last.current = { x: e.clientX, y: e.clientY };
    setCam((c) => ({ ...c, x: c.x + dx, y: c.y + dy }));
  }, []);

  const onMouseUp = useCallback(() => { panning.current = false; }, []);

  // Avisar al padre después del commit, nunca desde dentro del updater de
  // setCam: llamar un setState ajeno mientras React todavía está
  // resolviendo el de este componente dispara "Cannot update a component
  // while rendering a different component".
  useEffect(() => {
    onCameraChange?.(cam);
  }, [cam, onCameraChange]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [onWheel]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.addEventListener("mousedown", onMouseDown);
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => {
      el.removeEventListener("mousedown", onMouseDown);
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, [onMouseDown, onMouseMove, onMouseUp]);

  const handleClick = useCallback((e) => {
    if (moved.current) { moved.current = false; return; }

    // Mismo criterio de "espacio vacío" que usa onMouseDown para el pan: un
    // click que llegó hasta acá sin haber sido interceptado antes por una
    // ClassCard (que sí burbujea, al ser un hijo del Sheet) es un click en
    // el fondo del lienzo. onCanvasClick decide él mismo si hace algo con
    // eso (solo crea una clase si el modo insertar está activo); onEmptyClick
    // se dispara siempre en paralelo, para deseleccionar lo que hubiera
    // elegido -- clase o relación -- igual que en Miro/draw.io: clickear el
    // fondo limpia la selección aunque no se esté insertando nada.
    if (e.target !== e.currentTarget && e.target !== ref.current?.firstElementChild) return;

    onEmptyClick?.();

    if (!onCanvasClick) return;
    const rect = ref.current?.getBoundingClientRect();
    if (!rect) return;
    const localX = e.clientX - rect.left;
    const localY = e.clientY - rect.top;
    const worldPxX = (localX - cam.x) / cam.z;
    const worldPxY = (localY - cam.y) / cam.z;
    const x_grid = Math.max(0, Math.round(worldPxX / CELL));
    const y_grid = Math.max(0, Math.round(worldPxY / CELL));
    onCanvasClick({ x_grid, y_grid });
  }, [onCanvasClick, onEmptyClick, cam.x, cam.y, cam.z, CELL]);

  // Cursores en vivo (estilo Miro): reporto mi posición en coordenadas del
  // "mundo" del diagrama, la misma transformación que ya usa handleClick.
  // No hace falta un listener aparte: cualquier movimiento sobre el
  // lienzo ya pasa por acá.
  const handleMouseMoveForCursor = useCallback((e) => {
    if (!onCursorMove) return;
    const rect = ref.current?.getBoundingClientRect();
    if (!rect) return;
    const localX = e.clientX - rect.left;
    const localY = e.clientY - rect.top;
    // Dividimos también por CELL, igual que handleClick: lo que viaja por el
    // WebSocket tiene que ser coordenadas de grilla (world / CELL), no
    // "world pixels" sin escalar -- RemoteCursor multiplica por CELL para
    // volver a pixeles de pantalla, así que mandar world pixels acá hacía
    // que el cursor remoto terminara CELL veces más lejos de lo real (con
    // CELL=16, a kilómetros fuera de cualquier viewport visible).
    onCursorMove(
      (localX - cam.x) / cam.z / CELL,
      (localY - cam.y) / cam.z / CELL
    );
  }, [onCursorMove, cam.x, cam.y, cam.z, CELL]);

  // Pizarra "infinita": en vez de un rectángulo de tamaño fijo, la grilla es
  // un patrón de fondo que se repite en todo el área visible y se desplaza
  // con la cámara -- así nunca hay un borde real donde el lienzo "se
  // termine". Las clases no tienen límite máximo de posición (solo el
  // mínimo, en handleClick, para no crearlas en coordenadas negativas).
  const gridCell = CELL * cam.z;
  return (
    <div
      ref={ref}
      onClick={handleClick}
      onMouseMove={handleMouseMoveForCursor}
      style={{
        position: "relative",
        width: "100%",
        height: "100%",
        overflow: "hidden",
        background: "var(--surface-1)",
        backgroundImage:
          "linear-gradient(var(--border) 1px, transparent 1px), linear-gradient(90deg, var(--border) 1px, transparent 1px)",
        backgroundSize: `${gridCell}px ${gridCell}px`,
        backgroundPosition: `${cam.x}px ${cam.y}px`,
        userSelect: panning.current ? "none" : undefined,
        cursor: panning.current ? "grabbing" : "grab",
      }}
      title="Pan: arrastrá el espacio vacío, rueda o Ctrl+arrastrar | Zoom: rueda | Click: acción del padre"
    >
      <div
        style={{
          position: "absolute",
          left: cam.x,
          top: cam.y,
          transform: `scale(${cam.z})`,
          transformOrigin: "0 0",
        }}
      >
        {children}

        {/* Cursores en vivo de otros colaboradores. Van dentro de este
            mismo div (ya transformado por cam.x/cam.y/cam.z) para no
            tener que repetir la conversión mundo->pantalla acá.
            El z-index de cada ClassCard (cls.z_index) las saca del flujo
            normal, así que sin este wrapper -- que tiene su PROPIO
            z-index alto a este mismo nivel -- el cursor quedaba tapado
            por cualquier tarjeta con z-index explícito, aunque el div del
            cursor en sí tuviera un z-index más alto (ese z-index solo
            compite dentro de su propio stacking context). */}
        <div style={{ position: "absolute", inset: 0, zIndex: 999, pointerEvents: "none" }}>
          {remoteCursors.map((c) => (
            <RemoteCursor key={c.conn_id} cursor={c} />
          ))}
        </div>
      </div>
    </div>
  );
}

/** Puntero de otro colaborador con su nombre y, si aplica, qué está
 * haciendo. La transición CSS suaviza el salto entre las posiciones que
 * llegan cada ~50ms, para que el movimiento se vea fluido y no a los tirones. */
function RemoteCursor({ cursor }) {
  const { x, y, name, color, label } = cursor;
  return (
    <div
      style={{
        position: "absolute",
        left: x * SHEET.CELL,
        top: y * SHEET.CELL,
        pointerEvents: "none",
        zIndex: 50,
        transition: "left 80ms linear, top 80ms linear",
        willChange: "left, top",
      }}
    >
      <svg width="20" height="20" viewBox="0 0 20 20" style={{ display: "block", filter: "drop-shadow(0 1px 2px rgba(0,0,0,.35))" }}>
        <path d="M2 1 L2 17 L6.5 13.5 L9.5 19 L12 17.5 L9 12 L15 12 Z" fill={color} stroke="var(--surface-1)" strokeWidth="1" />
      </svg>
      <div
        style={{
          marginTop: 2,
          marginLeft: 14,
          display: "inline-flex",
          flexDirection: "column",
          gap: 2,
          whiteSpace: "nowrap",
        }}
      >
        <span
          style={{
            fontSize: 11,
            fontWeight: 600,
            color: "#fff",
            background: color,
            padding: "2px 6px",
            borderRadius: 4,
            boxShadow: "0 1px 3px rgba(0,0,0,.3)",
          }}
        >
          {name}
        </span>
        {label && (
          <span
            style={{
              fontSize: 10,
              color: "var(--text-muted)",
              background: "var(--surface-2)",
              border: "1px solid var(--border)",
              padding: "1px 5px",
              borderRadius: 4,
              width: "fit-content",
            }}
          >
            {label}
          </span>
        )}
      </div>
    </div>
  );
}
