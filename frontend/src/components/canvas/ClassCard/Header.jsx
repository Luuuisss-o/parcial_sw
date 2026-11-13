import Icon from "../../common/Icon";

// UML 2.5: las interfaces y enumeraciones llevan su estereotipo sobre el
// nombre; las clases abstractas (y las interfaces) van en cursiva.
//
// Aspecto sobrio, como Enterprise Architect: estereotipo y nombre centrados,
// nombre en negrita, encabezado separado del compartimento de atributos por
// una línea. El botón del ojo solo aparece al pasar el mouse (o si está fijado).
const STEREOTYPE = { interface: "«interface»", enumeration: "«enumeration»" };

export default function Header({
  innerRef,
  onMouseDown,
  title,
  kind = "class",
  pinned,
  setPinned,
  lockedByOther = null,
  hover = false,
}) {
  return (
    <div
      ref={innerRef}
      onMouseDown={onMouseDown}
      style={{
        position: "relative",
        padding: "5px 24px",
        fontSize: 12.5,
        background: "var(--uml-class-header-bg)",
        borderBottom: "1px solid var(--uml-class-border)",
        cursor: lockedByOther ? "not-allowed" : "grab",
        userSelect: "none",
        textAlign: "center",
        lineHeight: 1.3,
      }}
      title={lockedByOther ? `La está editando ${lockedByOther}` : "Arrastrá para mover esta clase"}
    >
      {STEREOTYPE[kind] && (
        <div
          data-testid="class-stereotype"
          style={{ fontSize: 10.5, color: "var(--uml-class-muted)" }}
        >
          {STEREOTYPE[kind]}
        </div>
      )}
      <div
        style={{
          fontWeight: 700,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
          fontStyle: kind === "abstract" || kind === "interface" ? "italic" : "normal",
        }}
        title={kind === "abstract" ? "Clase abstracta" : undefined}
      >
        {title}
      </div>

      {lockedByOther && (
        <span
          title={`La está editando ${lockedByOther}`}
          style={{ position: "absolute", left: 6, top: 6, display: "grid", color: "var(--warning)" }}
        >
          <Icon name="lock" size={12} />
        </span>
      )}

      <button
        type="button"
        onMouseDown={(e) => e.stopPropagation()}
        onClick={(e) => {
          e.stopPropagation();
          setPinned((v) => !v);
        }}
        title={pinned ? "Dejar de mostrar siempre los detalles" : "Mostrar siempre los detalles"}
        style={{
          position: "absolute",
          right: 4,
          top: 4,
          display: "grid",
          placeItems: "center",
          width: 18,
          height: 18,
          border: "none",
          background: "transparent",
          color: pinned ? "var(--uml-class-select)" : "var(--uml-class-muted)",
          padding: 0,
          cursor: "pointer",
          opacity: hover || pinned ? 1 : 0,
          transition: "opacity .15s",
        }}
      >
        <Icon name={pinned ? "eye" : "eyeOff"} size={12} />
      </button>
    </div>
  );
}
