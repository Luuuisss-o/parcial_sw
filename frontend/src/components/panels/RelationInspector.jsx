// src/components/panels/RelationInspector.jsx
//
// Panel derecho cuando hay una relación seleccionada. fullUpdate manda
// siempre el objeto completo porque el PATCH del backend interpreta los
// campos ausentes. Igual que el Inspector de clase, no hay botón "Guardar":
// cada cambio se persiste solo, vía useAutoSave, que muestra el estado
// (Guardando/Guardado) en el encabezado y el error en el panel si el
// servidor lo rechaza, en vez de perderlo en un alert().
//
// También igual que el Inspector de clase, se puede plegar a una franja
// angosta (el diagrama puede tener relaciones largas que cruzan medio
// lienzo, y a veces el panel tapa justo la zona que se quiere ver).

import { useState, useEffect } from "react";
import Icon from "../common/Icon";
import { SaveStatus, RowError } from "../common/SaveStatus";
import useAutoSave from "../../hooks/useAutoSave";

const COLLAPSE_KEY = "uml.relationInspector.collapsed";

function useDebouncedCallback(callback, delay) {
  const [timeoutId, setTimeoutId] = useState(null);
  return function debounced(...args) {
    if (timeoutId) clearTimeout(timeoutId);
    const id = setTimeout(() => callback(...args), delay);
    setTimeoutId(id);
  };
}

const TIPOS = [
  { v: "ASSOCIATION", label: "Asociación", ayuda: "Se relacionan, pero cada una existe por su cuenta." },
  { v: "AGGREGATION", label: "Agregación", ayuda: "Una agrupa a la otra, que igual sobrevive sin ella." },
  { v: "COMPOSITION", label: "Composición", ayuda: "Una contiene a la otra; sin la primera, la otra no existe." },
  { v: "INHERITANCE", label: "Herencia (generalización)", ayuda: "El origen es un tipo especializado del destino (la flecha apunta al padre)." },
  { v: "REALIZATION", label: "Realización", ayuda: "El origen implementa la interfaz del destino." },
  { v: "DEPENDENCY", label: "Dependencia", ayuda: "El origen usa al destino de forma puntual." },
];

// Relaciones que no son asociaciones: sin multiplicidad, roles ni navegabilidad.
const SIN_EXTREMOS = ["INHERITANCE", "DEPENDENCY", "REALIZATION"];

const ANCHORS = [
  { v: "left", label: "Izquierda" },
  { v: "right", label: "Derecha" },
  { v: "top", label: "Arriba" },
  { v: "bottom", label: "Abajo" },
];

/** Vista previa en miniatura de cómo se ve cada tipo de relación en el
 * diagrama: la misma notación UML que dibuja ConnectionLayer, a escala
 * chica, para que elegir el tipo no dependa de recordar qué es cada uno. */
function RelationTypePreview({ type }) {
  const color = "var(--accent)";
  const common = { stroke: color, strokeWidth: 1.8, strokeLinecap: "round" };
  let marker = null;
  let dashed = false;

  switch (type) {
    case "INHERITANCE":
      marker = (
        <path d="M 44 8 L 58 4 L 44 0 z" fill="var(--surface-1)" stroke={color} strokeWidth="1.4" strokeLinejoin="round" />
      );
      break;
    case "AGGREGATION":
      marker = (
        <path d="M 44 8 L 34 4 L 44 0 L 54 4 z" fill="var(--surface-1)" stroke={color} strokeWidth="1.4" strokeLinejoin="round" />
      );
      break;
    case "COMPOSITION":
      marker = (
        <path d="M 44 8 L 34 4 L 44 0 L 54 4 z" fill={color} />
      );
      break;
    case "REALIZATION":
      dashed = true;
      marker = (
        <path d="M 44 8 L 58 4 L 44 0 z" fill="var(--surface-1)" stroke={color} strokeWidth="1.4" strokeLinejoin="round" />
      );
      break;
    case "DEPENDENCY":
      dashed = true;
      // Flecha abierta (UML 2.5)
      marker = <path d="M 48 0.5 L 57 4 L 48 7.5" fill="none" stroke={color} strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />;
      break;
    default: // ASSOCIATION
      marker = null;
  }

  return (
    <svg viewBox="0 0 60 8" width="60" height="8" style={{ flexShrink: 0 }}>
      <line x1="2" y1="4" x2="58" y2="4" {...common} strokeDasharray={dashed ? "4,3" : undefined} />
      {marker}
    </svg>
  );
}

export default function RelationInspector({ relation, onUpdate, onDelete, readOnly = false }) {
  const [localLabel, setLocalLabel] = useState(relation?.label ?? "");
  const [localMultOrigenMin, setLocalMultOrigenMin] = useState(relation?.src_mult_min ?? "");
  const [localMultOrigenMax, setLocalMultOrigenMax] = useState(
    relation?.src_mult_max === null ? "*" : relation?.src_mult_max ?? ""
  );
  const [localMultDestinoMin, setLocalMultDestinoMin] = useState(relation?.dst_mult_min ?? "");
  const [localMultDestinoMax, setLocalMultDestinoMax] = useState(
    relation?.dst_mult_max === null ? "*" : relation?.dst_mult_max ?? ""
  );
  // UML 2.5: nombre de rol de cada extremo
  const [localSrcRole, setLocalSrcRole] = useState(relation?.src_role ?? "");
  const [localDstRole, setLocalDstRole] = useState(relation?.dst_role ?? "");

  useEffect(() => {
    if (!relation) return;
    setLocalLabel(relation.label ?? "");
    setLocalMultOrigenMin(relation.src_mult_min ?? "");
    setLocalMultOrigenMax(relation.src_mult_max === null ? "*" : relation.src_mult_max);
    setLocalMultDestinoMin(relation.dst_mult_min ?? "");
    setLocalMultDestinoMax(relation.dst_mult_max === null ? "*" : relation.dst_mult_max);
    setLocalSrcRole(relation.src_role ?? "");
    setLocalDstRole(relation.dst_role ?? "");
  }, [
    relation?.id,
    relation?.label,
    relation?.src_mult_min,
    relation?.src_mult_max,
    relation?.dst_mult_min,
    relation?.dst_mult_max,
    relation?.src_role,
    relation?.dst_role,
  ]);

  // Sin delay propio: los selects e inputs numéricos de este panel ya se
  // guardan al toque (como siempre hicieron), y la etiqueta tiene su propio
  // debounce manual más abajo antes de llegar acá. useAutoSave(0) solo
  // aporta el estado visible (Guardando/Guardado/error), no un retraso.
  //
  // Se llama ACÁ, antes del early return de "no hay relación seleccionada"
  // de más abajo: las reglas de hooks exigen que se invoquen siempre en el
  // mismo orden en cada render, y ese return temprano es condicional.
  const { save, status, error } = useAutoSave(0);

  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(COLLAPSE_KEY) === "1");
  useEffect(() => {
    localStorage.setItem(COLLAPSE_KEY, collapsed ? "1" : "0");
  }, [collapsed]);

  const fullUpdate = (patch) => {
    if (!relation) return;
    const body = {
      type: patch.type ?? relation.type,
      label: patch.label ?? localLabel ?? relation.label ?? "",
      src_anchor: patch.src_anchor ?? relation.src_anchor ?? "right",
      dst_anchor: patch.dst_anchor ?? relation.dst_anchor ?? "left",
      src_offset: patch.src_offset ?? relation.src_offset ?? 0,
      dst_offset: patch.dst_offset ?? relation.dst_offset ?? 0,
      src_lane: patch.src_lane ?? relation.src_lane ?? 0,
      dst_lane: patch.dst_lane ?? relation.dst_lane ?? 0,
      src_mult_min: patch.src_mult_min ?? (localMultOrigenMin === "" ? null : Number(localMultOrigenMin)),
      src_mult_max: patch.src_mult_max ?? (localMultOrigenMax === "*" ? null : Number(localMultOrigenMax)),
      dst_mult_min: patch.dst_mult_min ?? (localMultDestinoMin === "" ? null : Number(localMultDestinoMin)),
      dst_mult_max: patch.dst_mult_max ?? (localMultDestinoMax === "*" ? null : Number(localMultDestinoMax)),
      src_role: "src_role" in patch ? patch.src_role : localSrcRole,
      dst_role: "dst_role" in patch ? patch.dst_role : localDstRole,
      src_navigable: patch.src_navigable ?? !!relation.src_navigable,
      dst_navigable: patch.dst_navigable ?? !!relation.dst_navigable,
    };
    save(() => onUpdate(body));
  };

  const debouncedUpdate = useDebouncedCallback((val) => fullUpdate({ label: val }), 400);
  const debouncedSrcRole = useDebouncedCallback((val) => fullUpdate({ src_role: val }), 400);
  const debouncedDstRole = useDebouncedCallback((val) => fullUpdate({ dst_role: val }), 400);

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

  if (!relation) {
    return (
      <aside style={asideStyle}>
        <div style={{ display: "flex", justifyContent: "flex-end", padding: "var(--sp-2) var(--sp-2) 0" }}>
          <CollapseToggle />
        </div>
        <div className="text-muted" style={{ margin: "auto", fontSize: 13 }}>
          Seleccioná una relación para editarla.
        </div>
      </aside>
    );
  }

  const tipoActual = TIPOS.find((t) => t.v === relation.type);
  const esHerenciaODependencia = SIN_EXTREMOS.includes(relation.type);

  return (
    <aside style={asideStyle}>
      {/* ---------- Encabezado ---------- */}
      {/* El botón de plegar va en su PROPIA fila, separado del resto: el
          panel tiene ancho fijo (var(--inspector-w)) y, con el ícono, el
          título, el estado de guardado, el badge del tipo y "Eliminar" todos
          compitiendo en una sola fila, el botón de plegar (al ser el último)
          terminaba empujado fuera y oculto por overflow en pantallas de
          ancho normal -- solo se veía en un viewport artificialmente ancho. */}
      <div style={{ display: "flex", justifyContent: "flex-end", padding: "var(--sp-2) var(--sp-2) 0" }}>
        <CollapseToggle />
      </div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--sp-2)",
          padding: "0 var(--sp-4) var(--sp-4)",
        }}
      >
        <Icon name="relation" size={15} style={{ color: "var(--accent)", flexShrink: 0 }} />
        <div style={{ flex: 1, minWidth: 0, display: "flex", alignItems: "center", gap: "var(--sp-2)" }}>
          <strong style={{ fontSize: 13, whiteSpace: "nowrap" }}>Relación</strong>
          <SaveStatus status={status} />
        </div>
        {tipoActual && (
          <span
            style={{
              fontSize: 11,
              fontWeight: 600,
              padding: "2px var(--sp-2)",
              borderRadius: 999,
              background: "var(--accent-soft)",
              color: "var(--accent)",
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
              flexShrink: 1,
              minWidth: 0,
            }}
          >
            {tipoActual.label}
          </span>
        )}
        {!readOnly && (
          <button
            className="btn btn-danger-ghost btn-icon btn-sm"
            onClick={onDelete}
            title="Eliminar esta relación"
            style={{ flexShrink: 0 }}
          >
            <Icon name="trash" size={14} />
          </button>
        )}
      </div>
      <div style={{ borderBottom: "1px solid var(--border)" }} />

      <fieldset
        disabled={readOnly}
        className="scroll"
        style={{ flex: 1, padding: "var(--sp-4)", display: "grid", gap: "var(--sp-5)", alignContent: "start",
                 border: 0, margin: 0, minWidth: 0, minHeight: 0 }}
      >
        <RowError message={error} />

        {/* Quiénes se conectan */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: "var(--sp-3)",
            padding: "var(--sp-4) var(--sp-3)",
            borderRadius: "var(--radius)",
            border: "1px solid var(--border)",
            background: "var(--surface-2)",
            fontSize: 13,
          }}
        >
          <span
            style={{
              padding: "var(--sp-1) var(--sp-2)",
              borderRadius: "var(--radius-sm)",
              background: "var(--surface-3)",
              fontWeight: 600,
            }}
          >
            {relation.origen_nombre}
          </span>
          <RelationTypePreview type={relation.type} />
          <span
            style={{
              padding: "var(--sp-1) var(--sp-2)",
              borderRadius: "var(--radius-sm)",
              background: "var(--surface-3)",
              fontWeight: 600,
            }}
          >
            {relation.destino_nombre}
          </span>
        </div>

        {/* Tipo */}
        <div className="field">
          <label className="label">Tipo de relación</label>
          <select className="select" value={relation.type} onChange={(e) => fullUpdate({ type: e.target.value })}>
            {TIPOS.map((t) => (
              <option key={t.v} value={t.v}>{t.label}</option>
            ))}
          </select>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "var(--sp-3)",
              padding: "var(--sp-2) var(--sp-3)",
              borderRadius: "var(--radius)",
              background: "var(--surface-2)",
            }}
          >
            <RelationTypePreview type={relation.type} />
            {tipoActual && (
              <div className="text-subtle" style={{ fontSize: 12, flex: 1 }}>{tipoActual.ayuda}</div>
            )}
          </div>
        </div>

        {/* Multiplicidad */}
        <div style={{ display: "grid", gap: "var(--sp-3)" }}>
          <h4 className="section-title">Multiplicidad</h4>

          {esHerenciaODependencia ? (
            <div className="text-subtle" style={{ fontSize: 12 }}>
              La herencia, la realización y la dependencia no llevan multiplicidad.
            </div>
          ) : (
            <>
              <div className="text-subtle" style={{ fontSize: 12 }}>
                Cuántos elementos de cada lado participan. Usá <strong>*</strong> para “muchos”.
              </div>

              {[
                {
                  titulo: relation.origen_nombre,
                  min: localMultOrigenMin,
                  max: localMultOrigenMax,
                  setMin: setLocalMultOrigenMin,
                  setMax: setLocalMultOrigenMax,
                  keyMin: "src_mult_min",
                  keyMax: "src_mult_max",
                },
                {
                  titulo: relation.destino_nombre,
                  min: localMultDestinoMin,
                  max: localMultDestinoMax,
                  setMin: setLocalMultDestinoMin,
                  setMax: setLocalMultDestinoMax,
                  keyMin: "dst_mult_min",
                  keyMax: "dst_mult_max",
                },
              ].map((lado) => (
                <div
                  key={lado.keyMin}
                  style={{
                    display: "grid",
                    gap: "var(--sp-2)",
                    padding: "var(--sp-3)",
                    border: "1px solid var(--border)",
                    borderRadius: "var(--radius)",
                    background: "var(--surface-2)",
                  }}
                >
                  <div style={{ fontSize: 12, fontWeight: 600 }}>Lado {lado.titulo}</div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--sp-2)" }}>
                    <div className="field">
                      <label className="label">Mínimo</label>
                      <input
                        className="input input-sm"
                        type="number"
                        min={0}
                        value={lado.min}
                        onChange={(e) => {
                          const val = e.target.value === "" ? null : Number(e.target.value);
                          lado.setMin(e.target.value);
                          fullUpdate({ [lado.keyMin]: val });
                        }}
                      />
                    </div>
                    <div className="field">
                      <label className="label">Máximo</label>
                      <input
                        className="input input-sm"
                        type="text"
                        value={lado.max === null ? "*" : lado.max}
                        onChange={(e) => {
                          const raw = e.target.value;
                          const val = raw === "*" || raw === "" ? null : Number(raw);
                          lado.setMax(raw);
                          fullUpdate({ [lado.keyMax]: val });
                        }}
                      />
                    </div>
                  </div>
                </div>
              ))}
            </>
          )}
        </div>

        {/* Roles y navegabilidad (UML 2.5) */}
        {!esHerenciaODependencia && (
          <div style={{ display: "grid", gap: "var(--sp-3)" }}>
            <h4 className="section-title">Extremos (roles y navegabilidad)</h4>
            <div className="text-subtle" style={{ fontSize: 12 }}>
              El rol es el nombre con el que una clase ve a la otra. Un extremo navegable se dibuja con
              una flecha abierta.
            </div>
            {[
              {
                titulo: relation.origen_nombre,
                role: localSrcRole,
                setRole: setLocalSrcRole,
                saveRole: debouncedSrcRole,
                nav: !!relation.src_navigable,
                keyNav: "src_navigable",
              },
              {
                titulo: relation.destino_nombre,
                role: localDstRole,
                setRole: setLocalDstRole,
                saveRole: debouncedDstRole,
                nav: !!relation.dst_navigable,
                keyNav: "dst_navigable",
              },
            ].map((lado) => (
              <div
                key={lado.keyNav}
                style={{
                  display: "grid",
                  gap: "var(--sp-2)",
                  padding: "var(--sp-3)",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--radius)",
                  background: "var(--surface-2)",
                }}
              >
                <div style={{ fontSize: 12, fontWeight: 600 }}>Extremo {lado.titulo}</div>
                <input
                  className="input input-sm"
                  value={lado.role}
                  placeholder="Rol (opcional, ej: cliente)"
                  onChange={(e) => {
                    lado.setRole(e.target.value);
                    lado.saveRole(e.target.value);
                  }}
                />
                <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, cursor: "pointer" }}>
                  <input
                    type="checkbox"
                    checked={lado.nav}
                    onChange={(e) => fullUpdate({ [lado.keyNav]: e.target.checked })}
                  />
                  <span className="text-muted">Navegable hacia {lado.titulo}</span>
                </label>
              </div>
            ))}
          </div>
        )}

        {/* Etiqueta */}
        <div className="field">
          <label className="label">Etiqueta (opcional)</label>
          <input
            className="input"
            type="text"
            value={localLabel}
            placeholder="Ej: realiza, pertenece a"
            onChange={(e) => {
              setLocalLabel(e.target.value);
              debouncedUpdate(e.target.value);
            }}
          />
          <div className="text-subtle" style={{ fontSize: 12 }}>
            Texto que se muestra sobre la línea en el diagrama.
          </div>
        </div>

        {/* Posición de la línea */}
        <div style={{ display: "grid", gap: "var(--sp-3)" }}>
          <h4 className="section-title">Posición de la línea</h4>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--sp-2)" }}>
            <div className="field">
              <label className="label">Sale por</label>
              <select
                className="select input-sm"
                value={relation.src_anchor ?? "right"}
                onChange={(e) => fullUpdate({ src_anchor: e.target.value })}
              >
                {ANCHORS.map((a) => (
                  <option key={a.v} value={a.v}>{a.label}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label className="label">Llega por</label>
              <select
                className="select input-sm"
                value={relation.dst_anchor ?? "left"}
                onChange={(e) => fullUpdate({ dst_anchor: e.target.value })}
              >
                {ANCHORS.map((a) => (
                  <option key={a.v} value={a.v}>{a.label}</option>
                ))}
              </select>
            </div>
          </div>
        </div>
      </fieldset>
    </aside>
  );
}
