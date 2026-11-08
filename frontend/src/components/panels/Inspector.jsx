// src/components/panels/Inspector.jsx
//
// Panel derecho: edición de la clase seleccionada (nombre, atributos y
// métodos).
//
// No hay botón "Guardar": cada campo se guarda solo, con un pequeño retraso
// para no disparar una petición por tecla, y muestra el estado del guardado.
// Si el servidor rechaza el cambio (por ejemplo un nombre repetido dentro de
// la clase) el error se muestra en la fila correspondiente, en vez de
// descartarse en silencio como pasaba antes.

import { useEffect, useRef, useState } from "react";
import { updateClass } from "../../api/classes";
import useAutoSave from "../../hooks/useAutoSave";
import Icon from "../common/Icon";
import { SaveStatus, RowError } from "../common/SaveStatus";

const TYPE_OPTIONS = [
  { v: "string", label: "Texto (string)" },
  { v: "text", label: "Texto largo (text)" },
  { v: "int", label: "Número entero (int)" },
  { v: "float", label: "Número decimal (float)" },
  { v: "decimal", label: "Decimal exacto (decimal)" },
  { v: "boolean", label: "Sí / No (boolean)" },
  { v: "date", label: "Fecha (date)" },
  { v: "datetime", label: "Fecha y hora (datetime)" },
  { v: "uuid", label: "Identificador (uuid)" },
  { v: "email", label: "Correo (email)" },
];

/** Caja de un atributo: nombre, tipo y obligatoriedad. */
function AttributeRow({ attr, onPatch, onRemove }) {
  const serverName = attr.name ?? attr.nombre ?? "";
  const [name, setName] = useState(serverName);
  const inputRef = useRef(null);
  const { save, status, error } = useAutoSave();

  // Tipo y obligatoriedad se editan de una vez (un select o un click, no
  // tecla por tecla como el nombre), así que no hace falta debounce: se
  // guardan al toque y muestran estado optimista para no depender de que
  // vuelva la respuesta del servidor antes de reflejar el cambio.
  const [type, setType] = useState(attr.type ?? attr.tipo ?? "string");
  const [required, setRequired] = useState(!!attr.required);
  const { save: saveNow, status: statusNow, error: errorNow } = useAutoSave(0);

  // Sincroniza si el valor cambió en el servidor (otro usuario, o el
  // asistente de IA) mientras no lo estamos editando nosotros.
  useEffect(() => {
    if (document.activeElement !== inputRef.current) setName(serverName);
  }, [serverName]);
  useEffect(() => { setType(attr.type ?? attr.tipo ?? "string"); }, [attr.type, attr.tipo]);
  useEffect(() => { setRequired(!!attr.required); }, [attr.required]);

  return (
    <div
      style={{
        display: "grid",
        gap: "var(--sp-2)",
        padding: "var(--sp-3)",
        border: `1px solid ${error || errorNow ? "var(--danger)" : "var(--border)"}`,
        borderRadius: "var(--radius)",
        background: "var(--surface-2)",
      }}
    >
      <div style={{ display: "flex", gap: "var(--sp-2)", alignItems: "center" }}>
        <input
          ref={inputRef}
          className="input input-sm"
          value={name}
          onChange={(e) => {
            const val = e.target.value;
            setName(val);
            save(() => onPatch({ name: val }));
          }}
          placeholder="Nombre del atributo"
        />
        <SaveStatus status={status} />
        <button className="btn btn-danger-ghost btn-icon btn-sm" onClick={onRemove} title="Eliminar atributo">
          <Icon name="trash" size={14} />
        </button>
      </div>

      <select
        className="select input-sm"
        value={type}
        onChange={(e) => {
          const val = e.target.value;
          setType(val);
          saveNow(() => onPatch({ type: val }));
        }}
      >
        {TYPE_OPTIONS.map((o) => (
          <option key={o.v} value={o.v}>{o.label}</option>
        ))}
      </select>

      <label
        style={{ display: "flex", alignItems: "center", gap: "var(--sp-2)", fontSize: 12, cursor: "pointer" }}
        title="Si está marcado, el campo será obligatorio (NOT NULL) en la base de datos"
      >
        <input
          type="checkbox"
          checked={required}
          onChange={(e) => {
            const val = e.target.checked;
            setRequired(val);
            saveNow(() => onPatch({ required: val }));
          }}
        />
        <span className="text-muted">Obligatorio (NOT NULL)</span>
        <SaveStatus status={statusNow} />
      </label>

      <RowError message={error || errorNow} />
    </div>
  );
}

/** Caja de un método: nombre y tipo de retorno. */
function MethodRow({ meth, onPatch, onRemove }) {
  const serverName = meth.name ?? meth.nombre ?? "";
  const [name, setName] = useState(serverName);
  const inputRef = useRef(null);
  const { save, status, error } = useAutoSave();

  useEffect(() => {
    if (document.activeElement !== inputRef.current) setName(serverName);
  }, [serverName]);

  return (
    <div
      style={{
        display: "grid",
        gap: "var(--sp-2)",
        padding: "var(--sp-3)",
        border: `1px solid ${error ? "var(--danger)" : "var(--border)"}`,
        borderRadius: "var(--radius)",
        background: "var(--surface-2)",
      }}
    >
      <div style={{ display: "flex", gap: "var(--sp-2)", alignItems: "center" }}>
        <input
          ref={inputRef}
          className="input input-sm"
          value={name}
          onChange={(e) => {
            const val = e.target.value;
            setName(val);
            save(() => onPatch({ name: val }));
          }}
          placeholder="Nombre del método"
        />
        <SaveStatus status={status} />
        <button className="btn btn-danger-ghost btn-icon btn-sm" onClick={onRemove} title="Eliminar método">
          <Icon name="trash" size={14} />
        </button>
      </div>

      <select
        className="select input-sm"
        value={meth.return_type ?? "void"}
        onChange={(e) => save(() => onPatch({ return_type: e.target.value }))}
      >
        <option value="void">Sin retorno (void)</option>
        {TYPE_OPTIONS.filter((o) => o.v !== "uuid").map((o) => (
          <option key={o.v} value={o.v}>{o.label}</option>
        ))}
      </select>

      <RowError message={error} />
    </div>
  );
}

const COLLAPSE_KEY = "uml.inspector.collapsed";

export default function Inspector({
  selected,
  details,
  onRename,
  onDeleteClass,
  reloadDetails,
  onAddAttr,
  onPatchAttr,
  onRemoveAttr,
  onAddMeth,
  onPatchMeth,
  onRemoveMeth,
}) {
  const [name, setName] = useState("");
  const [addError, setAddError] = useState("");
  const nameRef = useRef(null);
  const { save: saveName, status: nameStatus, error: nameError } = useAutoSave();

  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(COLLAPSE_KEY) === "1");
  useEffect(() => {
    localStorage.setItem(COLLAPSE_KEY, collapsed ? "1" : "0");
  }, [collapsed]);

  useEffect(() => {
    setAddError("");
    if (document.activeElement !== nameRef.current) setName(selected ? selected.name : "");
  }, [selected?.id, selected?.name]);

  const asideStyle = {
    width: collapsed ? "var(--inspector-collapsed-w, 44px)" : "var(--inspector-w)",
    borderLeft: "1px solid var(--border)",
    background: "var(--surface-1)",
    display: "flex",
    flexDirection: "column",
    position: "relative",
    zIndex: "var(--z-chrome)",
    transition: "width .15s ease",
  };

  const CollapseToggle = ({ style }) => (
    <button
      className="btn btn-ghost btn-icon btn-sm"
      onClick={() => setCollapsed((v) => !v)}
      title={collapsed ? "Desplegar panel" : "Plegar panel"}
      style={style}
    >
      <Icon name={collapsed ? "chevronLeft" : "chevronRight"} size={14} />
    </button>
  );

  // ---------- Plegado: franja angosta, sin importar si hay selección ----------
  if (collapsed) {
    return (
      <aside style={asideStyle}>
        <div style={{ padding: "var(--sp-3) var(--sp-2)", display: "flex", justifyContent: "center" }}>
          <CollapseToggle />
        </div>
      </aside>
    );
  }

  // ---------- Sin selección ----------
  if (!selected) {
    return (
      <aside style={asideStyle}>
        <div style={{ display: "flex", justifyContent: "flex-end", padding: "var(--sp-2) var(--sp-2) 0" }}>
          <CollapseToggle />
        </div>
        <div
          style={{
            margin: "auto",
            padding: "var(--sp-5)",
            textAlign: "center",
            display: "grid",
            gap: "var(--sp-3)",
            justifyItems: "center",
          }}
        >
          <div
            style={{
              width: 44, height: 44, display: "grid", placeItems: "center",
              borderRadius: "var(--radius)", background: "var(--surface-2)", color: "var(--text-subtle)",
            }}
          >
            <Icon name="cursor" size={20} />
          </div>
          <div style={{ fontSize: 13, fontWeight: 600 }}>Nada seleccionado</div>
          <div className="text-muted" style={{ fontSize: 12, maxWidth: 220 }}>
            Hacé clic en una clase del lienzo para ver y editar sus atributos y métodos acá.
          </div>
        </div>
      </aside>
    );
  }

  const runAdd = async (fn) => {
    setAddError("");
    try {
      await fn();
    } catch (e) {
      setAddError(e?.response?.data?.detail || "No se pudo agregar");
    }
  };

  return (
    <aside style={asideStyle}>
      {/* ---------- Encabezado ---------- */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--sp-2)",
          padding: "var(--sp-4)",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <Icon name="class" size={15} style={{ color: "var(--accent)" }} />
        <strong style={{ fontSize: 13, flex: 1 }}>Clase</strong>
        <button className="btn btn-danger-ghost btn-sm" onClick={onDeleteClass} title="Eliminar esta clase del diagrama">
          <Icon name="trash" size={14} />
          Eliminar
        </button>
        <CollapseToggle />
      </div>

      <div className="scroll" style={{ flex: 1, padding: "var(--sp-4)", display: "grid", gap: "var(--sp-5)", alignContent: "start" }}>
        {/* ---------- Nombre ---------- */}
        <div className="field">
          <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-2)" }}>
            <label className="label" style={{ flex: 1 }}>Nombre de la clase</label>
            <SaveStatus status={nameStatus} />
          </div>
          <input
            ref={nameRef}
            className="input"
            value={name}
            onChange={(e) => {
              const val = e.target.value;
              setName(val);
              saveName(async () => {
                const updated = await updateClass(selected.id, { name: val });
                onRename?.(updated.name);
              });
            }}
            placeholder="Ej: Cliente"
          />
          <RowError message={nameError} />
        </div>

        {/* ---------- Atributos ---------- */}
        <div style={{ display: "grid", gap: "var(--sp-3)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-2)" }}>
            <h4 className="section-title" style={{ flex: 1 }}>
              <Icon name="attribute" size={13} />
              Atributos
            </h4>
            <button
              className="btn btn-ghost btn-icon btn-sm"
              onClick={reloadDetails}
              disabled={!reloadDetails}
              title="Volver a cargar desde el servidor"
            >
              <Icon name="refresh" size={14} />
            </button>
            <button className="btn btn-sm" onClick={() => runAdd(() => onAddAttr(selected.id))} disabled={!details}>
              <Icon name="plus" size={14} />
              Agregar
            </button>
          </div>

          <RowError message={addError} />

          {!details ? (
            <div className="text-muted" style={{ fontSize: 12 }}>Cargando…</div>
          ) : details.attrs.length === 0 ? (
            <div className="text-subtle" style={{ fontSize: 12 }}>
              Esta clase no tiene atributos. Cada atributo se convierte en una columna de la
              tabla al generar el backend.
            </div>
          ) : (
            <div style={{ display: "grid", gap: "var(--sp-3)" }}>
              {details.attrs.map((a) => (
                <AttributeRow
                  key={a.id}
                  attr={a}
                  onPatch={(patch) => onPatchAttr(selected.id, a.id, patch)}
                  onRemove={() => onRemoveAttr(selected.id, a.id)}
                />
              ))}
            </div>
          )}
        </div>

        {/* ---------- Métodos ---------- */}
        <div style={{ display: "grid", gap: "var(--sp-3)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-2)" }}>
            <h4 className="section-title" style={{ flex: 1 }}>
              <Icon name="method" size={13} />
              Métodos
            </h4>
            <button className="btn btn-sm" onClick={() => runAdd(() => onAddMeth(selected.id))} disabled={!details}>
              <Icon name="plus" size={14} />
              Agregar
            </button>
          </div>

          {!details ? (
            <div className="text-muted" style={{ fontSize: 12 }}>Cargando…</div>
          ) : details.meths.length === 0 ? (
            <div className="text-subtle" style={{ fontSize: 12 }}>
              Sin métodos. Son opcionales: no afectan a las tablas generadas.
            </div>
          ) : (
            <div style={{ display: "grid", gap: "var(--sp-3)" }}>
              {details.meths.map((m) => (
                <MethodRow
                  key={m.id}
                  meth={m}
                  onPatch={(patch) => onPatchMeth(selected.id, m.id, patch)}
                  onRemove={() => onRemoveMeth(selected.id, m.id)}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ---------- Aclaración de guardado ---------- */}
      <div
        className="text-subtle"
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--sp-2)",
          padding: "var(--sp-3) var(--sp-4)",
          borderTop: "1px solid var(--border)",
          fontSize: 11,
        }}
      >
        <Icon name="check" size={13} />
        Los cambios se guardan solos. No hace falta apretar ningún botón.
      </div>
    </aside>
  );
}
