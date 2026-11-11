import Icon from "../../common/Icon";

// UML 2.5: las interfaces y enumeraciones llevan su estereotipo sobre el
// nombre; las clases abstractas (y las interfaces) van en cursiva.
const STEREOTYPE = { interface: "«interface»", enumeration: "«enumeration»" };

export default function Header({
  innerRef,
  onMouseDown,
  title,
  kind = "class",
  pinned,
  setPinned,
  showCounts,
  counts,
  lockedByOther = null,
}) {
  return (
    <div
      ref={innerRef}
      onMouseDown={onMouseDown}
      style={{
        padding: "8px 10px",
        fontWeight: 600,
        fontSize: 13,
        borderBottom: "1px solid var(--border)",
        cursor: lockedByOther ? "not-allowed" : "grab",
        userSelect: "none",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 8,
      }}
      title={lockedByOther ? `La está editando ${lockedByOther}` : "Arrastrá para mover esta clase"}
    >
      <span style={{ overflow: "hidden", display: "flex", alignItems: "center", gap: 6, minWidth: 0 }}>
        {lockedByOther && (
          <Icon name="lock" size={12} style={{ color: "var(--warning)", flexShrink: 0 }} />
        )}
        <span style={{ display: "grid", minWidth: 0, lineHeight: 1.25 }}>
          {STEREOTYPE[kind] && (
            <span
              data-testid="class-stereotype"
              style={{ fontSize: 10, fontWeight: 500, color: "var(--text-muted)" }}
            >
              {STEREOTYPE[kind]}
            </span>
          )}
          <span
            style={{
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              fontStyle: kind === "abstract" || kind === "interface" ? "italic" : "normal",
            }}
            title={kind === "abstract" ? "Clase abstracta" : undefined}
          >
            {title}
          </span>
        </span>
      </span>

      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        {lockedByOther && (
          <span
            className="text-subtle"
            style={{ fontSize: 11, maxWidth: 110, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
          >
            {lockedByOther}
          </span>
        )}
        {showCounts && (
          <span className="text-subtle" style={{ fontSize: 11 }}>
            {counts.attrs ?? 0} attrs · {counts.meths ?? 0} métodos
          </span>
        )}
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            setPinned((v) => !v);
          }}
          title={pinned ? "Dejar de mostrar siempre los detalles" : "Mostrar siempre los detalles"}
          style={{
            display: "grid",
            placeItems: "center",
            width: 22,
            height: 22,
            border: "1px solid var(--border)",
            background: pinned ? "var(--accent-soft)" : "transparent",
            color: pinned ? "var(--accent)" : "var(--text-subtle)",
            borderRadius: "var(--radius-sm)",
            padding: 0,
            cursor: "pointer",
          }}
        >
          <Icon name={pinned ? "eye" : "eyeOff"} size={13} />
        </button>
      </div>
    </div>
  );
}
