 //src/components/canvas/ClassCard/ClassCard.jsx
import { useMemo, useRef } from "react";
import { SHEET } from "../Sheet";
import Header from "./Header";
import Body from "./Body";
import Ports from "./Ports";
import useDragResize from "./useDragResize";
import useAutoGrow from "./useAutoGrow";

/** Debe coincidir con HIT en Ports.jsx */
const PORT_MARGIN = 22;

const CORNER_CURSOR = { nw: "nwse-resize", se: "nwse-resize", ne: "nesw-resize", sw: "nesw-resize" };
const CORNER_POS = {
  nw: { left: -3, top: -3 },
  ne: { right: -3, top: -3 },
  sw: { left: -3, bottom: -3 },
  se: { right: -3, bottom: -3 },
};
function cornerStyle(dir) {
  return {
    position: "absolute",
    ...CORNER_POS[dir],
    width: 10, height: 10,
    borderRadius: "50%",
    background: "var(--accent)",
    border: "1px solid var(--surface-1)",
    cursor: CORNER_CURSOR[dir],
    zIndex: 2,
  };
}

const EDGE_CURSOR = { n: "ns-resize", s: "ns-resize", e: "ew-resize", w: "ew-resize" };
function edgeStyle(dir) {
  const base = {
    position: "absolute",
    cursor: EDGE_CURSOR[dir],
    zIndex: 1,
  };
  switch (dir) {
    case "n": return { ...base, top: -5, left: 10, right: 10, height: 10 };
    case "s": return { ...base, bottom: -5, left: 10, right: 10, height: 10 };
    case "w": return { ...base, left: -5, top: 10, bottom: 10, width: 10 };
    case "e": return { ...base, right: -5, top: 10, bottom: 10, width: 10 };
    default: return base;
  }
}

/**
 * Props:
 *  - cls, details, selected, onSelect, onDragEnd, onResizeEnd
 *  - autoGrowHeight, minH, maxH, alwaysShowDetails
 *  - onStartLink(fromId, side, pt), showLinkPortsOnHover
 *  - forceShowPorts (nuevo): fuerza mostrar puertos (útil durante linking)
 */
export default function ClassCard({
  cls,
  details,
  selected = false,
  onSelect,
  onDragEnd,
  onResizeEnd,
  autoGrowHeight = true,
  minH = 4,
  maxH = 32,
  alwaysShowDetails = false,
  onStartLink,
  showLinkPortsOnHover = false,
  forceShowPorts = false, // ⬅️ nuevo
  lockedByOther = null,   // email de quien la tiene bloqueada, o null
}) {
  const { CELL } = SHEET;
  const headerRef = useRef(null);
  const bodyRef = useRef(null);

  // drag/resize
  const {
    pos, size, dragging,
    onHeaderMouseDown, onHandleMouseDown,
    setSize, setPinned,
    pinned, setHover, hover,
  } = useDragResize({
    cls, minH, maxH, CELL, onDragEnd, onResizeEnd,
  });

  const showDetails = alwaysShowDetails || pinned || selected;

  // auto grow
  useAutoGrow({
    enabled: autoGrowHeight && showDetails,
    headerRef, bodyRef, CELL, minH, maxH,
    size, setSize, onResizeEnd, clsId: cls.id,
  });

  const left = (pos.x ?? 0) * CELL;
  const top = (pos.y ?? 0) * CELL;
  const width = (size.w ?? 12) * CELL;
  const height = (size.h ?? 6) * CELL;

  const counts = useMemo(
    () => ({
      attrs: Array.isArray(details?.attrs) ? details.attrs.length : null,
      meths: Array.isArray(details?.meths) ? details.meths.length : null,
    }),
    [details]
  );
  const showCounts = !showDetails && (counts.attrs !== null || counts.meths !== null);

  // 👇 lógica final de visibilidad de puertos
  const showPorts = forceShowPorts || selected || (showLinkPortsOnHover && hover);

  return (
    <div
      data-class-id={cls.id}
      onMouseDown={() => onSelect?.(cls.id)}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        position: "absolute",
        left, top, width, height,
        overflow: "visible",       // 🔑 para que los puertos puedan “salir”
        zIndex: cls.z_index ?? 1,
        cursor: dragging ? "grabbing" : lockedByOther ? "not-allowed" : "default",
      }}
      title={
        lockedByOther
          ? `La está editando ${lockedByOther}`
          : selected ? "Seleccionada" : "Click para seleccionar"
      }
    >
      {/* HALO de hover (invisible), más grande que el card para cubrir los puertos */}
      <div
        style={{
          position: "absolute",
          left: -PORT_MARGIN,
          top: -PORT_MARGIN,
          width: width + PORT_MARGIN * 2,
          height: height + PORT_MARGIN * 2,
          background: "transparent",
          pointerEvents: "auto",   // recibe eventos fuera del card
        }}
      />

      {/* Caja visual del card */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: "var(--surface-1)",
          border: lockedByOther
            ? "2px solid var(--warning)"
            : selected ? "2px solid var(--accent)" : "1px solid var(--border-strong)",
          borderRadius: "var(--radius)",
          color: "var(--text)",
          boxShadow: lockedByOther
            ? "0 0 0 3px var(--warning-soft), var(--shadow)"
            : selected ? "0 0 0 3px var(--accent-soft), var(--shadow)" : "var(--shadow-sm)",
          overflow: "hidden",
          transition: "box-shadow .15s, border-color .15s, background .15s",
        }}
      >
        <Header
          innerRef={headerRef}
          onMouseDown={lockedByOther ? undefined : onHeaderMouseDown}
          title={cls.name ?? cls.nombre ?? "Clase"}
          pinned={pinned}
          setPinned={setPinned}
          showCounts={showCounts}
          counts={counts}
          lockedByOther={lockedByOther}
        />

        <Body innerRef={bodyRef} showDetails={showDetails} details={details} size={size} />
      </div>

      {/* Handles de resize: 4 bordes + 4 esquinas, para poder crecer en
          cualquier dirección (no solo hacia abajo-derecha). Van fuera de la
          "Caja visual" (que tiene overflow:hidden por los bordes redondeados)
          porque si no, la parte que sobresale del borde queda recortada y
          deja de recibir clicks. */}
      {!lockedByOther && (
        <>
          {/* Esquinas */}
          <div onMouseDown={(e) => onHandleMouseDown(e, "nw")} style={cornerStyle("nw")} title="Redimensionar" />
          <div onMouseDown={(e) => onHandleMouseDown(e, "ne")} style={cornerStyle("ne")} title="Redimensionar" />
          <div onMouseDown={(e) => onHandleMouseDown(e, "sw")} style={cornerStyle("sw")} title="Redimensionar" />
          <div onMouseDown={(e) => onHandleMouseDown(e, "se")} style={cornerStyle("se")} title="Redimensionar" />
          {/* Bordes */}
          <div onMouseDown={(e) => onHandleMouseDown(e, "n")} style={edgeStyle("n")} title="Redimensionar hacia arriba" />
          <div onMouseDown={(e) => onHandleMouseDown(e, "s")} style={edgeStyle("s")} title="Redimensionar hacia abajo" />
          <div onMouseDown={(e) => onHandleMouseDown(e, "w")} style={edgeStyle("w")} title="Redimensionar hacia la izquierda" />
          <div onMouseDown={(e) => onHandleMouseDown(e, "e")} style={edgeStyle("e")} title="Redimensionar hacia la derecha" />
        </>
      )}

      {/* Puertos */}
      <Ports
        visible={showPorts}
        onStartLink={(side, e) =>
          onStartLink?.(cls.id, side, { x: e.clientX, y: e.clientY })
        }
      />
    </div>
  );
}
