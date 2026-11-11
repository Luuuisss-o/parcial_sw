// Cuerpo de la tarjeta de clase: compartimentos de atributos y métodos con
// la notación de UML 2.5:
//
//   atributo:  [visibilidad] [/]nombre : tipo [multiplicidad] [= valor]
//   método:    [visibilidad] nombre(parámetros) : tipo
//
// Los miembros estáticos van subrayados y los métodos abstractos en
// cursiva. En una enumeración, el primer compartimento lista sus literales.
// El asterisco marca los campos obligatorios (NOT NULL en la base de datos
// generada); no es notación UML, es un dato propio del generador.

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
  listStyle: "none",
};

const lista = { margin: "0 0 10px", padding: 0 };

const vis = {
  display: "inline-block",
  width: 12,
  color: "var(--text-subtle)",
  fontFamily: "var(--font-mono)",
};

/** Texto UML de un atributo, sin la visibilidad (va en su propia columna). */
function formatAttribute(a) {
  let s = `${a.is_derived ? "/" : ""}${a.name ?? a.nombre} : ${a.type ?? a.tipo ?? "string"}`;
  if (a.multiplicity) s += ` [${a.multiplicity}]`;
  if (a.default_value) s += ` = ${a.default_value}`;
  return s;
}

/** Texto UML de un método, sin la visibilidad. */
function formatMethod(m) {
  return `${m.name ?? m.nombre}(${m.params ?? ""}) : ${m.return_type ?? m.tipo_retorno ?? "void"}`;
}

export default function Body({ innerRef, showDetails, details, size, kind = "class" }) {
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

  const esEnum = kind === "enumeration";

  return (
    <div ref={innerRef} style={{ padding: 10, fontSize: 12, lineHeight: 1.4, overflow: "hidden" }}>
      <div style={seccion}>{esEnum ? "Literales" : "Atributos"}</div>
      {details.attrs.length === 0 ? (
        <div className="text-subtle" style={{ marginBottom: 8 }}>
          {esEnum ? "Sin literales" : "Sin atributos"}
        </div>
      ) : (
        <ul style={lista}>
          {details.attrs.map((a) =>
            esEnum ? (
              <li key={a.id} style={item}>{a.name ?? a.nombre}</li>
            ) : (
              <li key={a.id} style={item} data-testid="uml-attribute">
                <span style={vis}>{a.visibility ?? "-"}</span>
                <span style={{ textDecoration: a.is_static ? "underline" : "none" }}>
                  {formatAttribute(a)}
                </span>
                {a.required ? (
                  <span style={{ color: "var(--warning)", marginLeft: 4 }} title="Obligatorio (NOT NULL)">
                    *
                  </span>
                ) : null}
              </li>
            )
          )}
        </ul>
      )}

      {/* En una enumeración el compartimento de métodos se omite si está vacío. */}
      {!(esEnum && details.meths.length === 0) && (
        <>
          <div style={seccion}>Métodos</div>
          {details.meths.length === 0 ? (
            <div className="text-subtle">Sin métodos</div>
          ) : (
            <ul style={{ ...lista, margin: 0 }}>
              {details.meths.map((m) => (
                <li key={m.id} style={item} data-testid="uml-method">
                  <span style={vis}>{m.visibility ?? "+"}</span>
                  <span
                    style={{
                      textDecoration: m.is_static ? "underline" : "none",
                      fontStyle: m.is_abstract || kind === "interface" ? "italic" : "normal",
                    }}
                  >
                    {formatMethod(m)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
