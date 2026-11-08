// Cuerpo de la tarjeta de clase: lista de atributos y métodos, con la
// notación habitual de UML (nombre : tipo). El asterisco marca los campos
// obligatorios (NOT NULL en la base de datos generada).

const seccion = {
  margin: "0 0 4px",
  fontSize: 10,
  fontWeight: 600,
  letterSpacing: "0.05em",
  textTransform: "uppercase",
  color: "var(--text-subtle)",
};

const item = {
  margin: "2px 0",
  whiteSpace: "nowrap",
  overflow: "hidden",
  textOverflow: "ellipsis",
};

export default function Body({ innerRef, showDetails, details, size }) {
  if (!showDetails) {
    return (
      <div ref={innerRef} className="text-subtle" style={{ padding: 10, fontSize: 11 }}>
        {size.w}×{size.h} celdas
      </div>
    );
  }

  if (!details) {
    return (
      <div ref={innerRef} className="text-muted" style={{ padding: 10, fontSize: 12 }}>
        Cargando…
      </div>
    );
  }

  return (
    <div ref={innerRef} style={{ padding: 10, fontSize: 12, lineHeight: 1.4, overflow: "hidden" }}>
      <div style={seccion}>Atributos</div>
      {details.attrs.length === 0 ? (
        <div className="text-subtle" style={{ marginBottom: 8 }}>
          Sin atributos
        </div>
      ) : (
        <ul style={{ margin: "0 0 10px", paddingLeft: 14 }}>
          {details.attrs.map((a) => (
            <li key={a.id} style={item}>
              {a.name ?? a.nombre}
              <span className="text-subtle"> : {a.type ?? a.tipo ?? "string"}</span>
              {a.required ? (
                <span style={{ color: "var(--warning)", marginLeft: 4 }} title="Obligatorio">
                  *
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      )}

      <div style={seccion}>Métodos</div>
      {details.meths.length === 0 ? (
        <div className="text-subtle">Sin métodos</div>
      ) : (
        <ul style={{ margin: 0, paddingLeft: 14 }}>
          {details.meths.map((m) => (
            <li key={m.id} style={item}>
              {m.name}
              <span className="text-subtle"> : {m.return_type ?? "void"}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
