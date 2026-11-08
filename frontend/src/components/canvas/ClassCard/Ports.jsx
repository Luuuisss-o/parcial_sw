// src/components/canvas/ClassCard/Ports.jsx

// Tamaño del hit-area (invisible); la flecha (triángulo) va dentro
const HIT = 22;

// Anclados al borde, y “saliendo” hacia afuera con translate
const PORTS = [
  { side: "top",    hitStyle: { top: 0,     left: "50%", transform: "translate(-50%, -100%)" }, arrow: { borderWidth: "8px 6px 0 6px", borderColor: "#ff3e3e transparent transparent transparent" } },
  { side: "right",  hitStyle: { right: 0,   top:  "50%", transform: "translate(100%, -50%)" },  arrow: { borderWidth: "6px 8px 6px 0", borderColor: "transparent #ff3e3e transparent transparent" } },
  { side: "bottom", hitStyle: { bottom: 0,  left: "50%", transform: "translate(-50%, 100%)" },  arrow: { borderWidth: "0 6px 8px 6px", borderColor: "transparent transparent #ff3e3e transparent" } },
  { side: "left",   hitStyle: { left: 0,    top:  "50%", transform: "translate(-100%, -50%)" }, arrow: { borderWidth: "6px 0 6px 8px", borderColor: "transparent transparent transparent #ff3e3e" } },
];

export default function Ports({ visible, onStartLink }) {
  if (!visible) return null;

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        pointerEvents: "none", // los hijos reactivan eventos
        zIndex: "var(--z-canvas)",
      }}
    >
      {PORTS.map((p) => (
        <div
          key={p.side}
          onMouseDown={(e) => {
            e.stopPropagation();
            onStartLink?.(p.side, e);
          }}
          title={`Iniciar relación desde ${p.side}`}
          style={{
            position: "absolute",
            width: HIT,
            height: HIT,
            ...p.hitStyle,
            background: "transparent",
            pointerEvents: "auto",
            cursor: "crosshair",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <span
            style={{
              display: "block",
              width: 0,
              height: 0,
              borderStyle: "solid",
              ...p.arrow,
              filter: "drop-shadow(0 0 6px rgba(255,62,62,.75))",
            }}
          />
        </div>
      ))}
    </div>
  );
}
