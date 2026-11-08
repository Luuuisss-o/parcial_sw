// src/components/panels/ImportFromPhotoModal.jsx
//
// Importar un diagrama de clases dibujado a mano (foto de pizarra/papel).
// Flujo en dos pasos, nunca automático de punta a punta: se sube la foto,
// Gemini transcribe lo que ve, y ANTES de crear nada se muestra esa lectura
// como una lista editable -- el usuario destilda lo que no quiere o corrige
// un nombre mal leído, y recién ahí confirma. El diagrama que existía ya lo
// diseñó una persona en la pizarra; esto solo lo digitaliza, no lo inventa.

import { useRef, useState } from "react";
import Icon from "../common/Icon";
import { detectDiagramFromImage, applyDetectedDiagram } from "../../api/vision";

const STEP = { PICK: "pick", REVIEW: "review", APPLYING: "applying" };

export default function ImportFromPhotoModal({ onClose, onImported }) {
  const [step, setStep] = useState(STEP.PICK);
  const [detecting, setDetecting] = useState(false);
  const [error, setError] = useState(null);
  const [preview, setPreview] = useState(null); // URL de la foto elegida
  const fileInputRef = useRef(null);

  const [title, setTitle] = useState("Diagrama importado");
  const [classes, setClasses] = useState([]); // [{ selected, name, attributes: [{selected, name, type, required}] }]
  const [relations, setRelations] = useState([]); // [{ selected, from_class, to_class, type, src_multiplicity, dst_multiplicity }]

  const handleFile = async (file) => {
    if (!file) return;
    setError(null);
    setPreview(URL.createObjectURL(file));
    setDetecting(true);
    try {
      const result = await detectDiagramFromImage(file);
      setClasses(
        (result.classes || []).map((c) => ({
          selected: true,
          name: c.name,
          attributes: (c.attributes || []).map((a) => ({ selected: true, ...a })),
        }))
      );
      setRelations((result.relations || []).map((r) => ({ selected: true, ...r })));
      if (result.warning) setError(result.warning);
      setStep(STEP.REVIEW);
    } catch (err) {
      setError(err?.response?.data?.detail || "No se pudo leer la imagen. Probá con otra foto, más nítida y de frente.");
    } finally {
      setDetecting(false);
    }
  };

  const toggleClass = (idx) => {
    setClasses((prev) => prev.map((c, i) => (i === idx ? { ...c, selected: !c.selected } : c)));
  };
  const toggleAttr = (ci, ai) => {
    setClasses((prev) =>
      prev.map((c, i) =>
        i !== ci ? c : { ...c, attributes: c.attributes.map((a, j) => (j === ai ? { ...a, selected: !a.selected } : a)) }
      )
    );
  };
  const toggleRelation = (idx) => {
    setRelations((prev) => prev.map((r, i) => (i === idx ? { ...r, selected: !r.selected } : r)));
  };
  const renameClass = (idx, name) => {
    setClasses((prev) => prev.map((c, i) => (i === idx ? { ...c, name } : c)));
  };

  const selectedClassNames = new Set(classes.filter((c) => c.selected).map((c) => c.name));

  const handleConfirm = async () => {
    setStep(STEP.APPLYING);
    setError(null);
    try {
      const body = {
        title: title.trim() || "Diagrama importado",
        classes: classes
          .filter((c) => c.selected && c.name.trim())
          .map((c) => ({
            name: c.name.trim(),
            attributes: c.attributes.filter((a) => a.selected && a.name.trim()).map((a) => ({
              name: a.name.trim(),
              type: a.type || "string",
              required: !!a.required,
            })),
          })),
        relations: relations
          .filter((r) => r.selected && selectedClassNames.has(r.from_class) && selectedClassNames.has(r.to_class))
          .map((r) => ({
            from_class: r.from_class,
            to_class: r.to_class,
            type: r.type,
            label: r.label || null,
            src_multiplicity: r.src_multiplicity || null,
            dst_multiplicity: r.dst_multiplicity || null,
          })),
      };
      const summary = await applyDetectedDiagram(body);
      onImported?.(summary.diagram_id);
    } catch (err) {
      setError(err?.response?.data?.detail || "No se pudo crear el diagrama");
      setStep(STEP.REVIEW);
    }
  };

  const totalSelectedClasses = classes.filter((c) => c.selected).length;

  return (
    <div className="modal-backdrop" onClick={step === STEP.APPLYING ? undefined : onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 560 }}>
        <div className="modal-header">
          <h2 className="modal-title">Importar desde foto</h2>
          {step !== STEP.APPLYING && (
            <button className="btn btn-ghost btn-icon" onClick={onClose} title="Cerrar">
              <Icon name="close" />
            </button>
          )}
        </div>

        <div className="modal-body scroll" style={{ display: "grid", gap: "var(--sp-4)" }}>
          {step === STEP.PICK && (
            <>
              <div className="text-muted" style={{ fontSize: 13 }}>
                Sacale una foto al diagrama de clases dibujado en la pizarra o en papel,
                bien de frente y con buena luz. El asistente va a leer las clases,
                atributos y relaciones que encuentre, y te va a mostrar el resultado
                antes de crear nada.
              </div>

              <input
                ref={fileInputRef}
                type="file"
                accept="image/jpeg,image/png,image/webp,image/heic,image/heif"
                capture="environment"
                style={{ display: "none" }}
                onChange={(e) => handleFile(e.target.files?.[0])}
              />

              {preview && (
                <img
                  src={preview}
                  alt="Foto elegida"
                  style={{ maxWidth: "100%", maxHeight: 240, borderRadius: "var(--radius)", border: "1px solid var(--border)", objectFit: "contain" }}
                />
              )}

              <button
                className="btn btn-primary"
                onClick={() => fileInputRef.current?.click()}
                disabled={detecting}
              >
                <Icon name={detecting ? "loader" : "upload"} className={detecting ? "spinning" : ""} />
                {detecting ? "Leyendo la imagen…" : preview ? "Elegir otra foto" : "Elegir foto"}
              </button>

              {error && (
                <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--danger)" }}>
                  <Icon name="warning" size={13} />
                  {error}
                </div>
              )}
            </>
          )}

          {(step === STEP.REVIEW || step === STEP.APPLYING) && (
            <>
              <div className="field">
                <label className="label">Título del diagrama nuevo</label>
                <input
                  className="input"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  disabled={step === STEP.APPLYING}
                />
              </div>

              {error && (
                <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--danger)" }}>
                  <Icon name="warning" size={13} />
                  {error}
                </div>
              )}

              <div className="text-subtle" style={{ fontSize: 12 }}>
                Esto es lo que se leyó de la foto. Destildá lo que no corresponda o
                corregí un nombre mal leído antes de crear el diagrama.
              </div>

              <div style={{ display: "grid", gap: "var(--sp-3)" }}>
                {classes.map((c, ci) => (
                  <div
                    key={ci}
                    style={{
                      border: "1px solid var(--border)",
                      borderRadius: "var(--radius)",
                      background: "var(--surface-2)",
                      padding: "var(--sp-3)",
                      display: "grid",
                      gap: "var(--sp-2)",
                      opacity: c.selected ? 1 : 0.5,
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-2)" }}>
                      <input
                        type="checkbox"
                        checked={c.selected}
                        onChange={() => toggleClass(ci)}
                        disabled={step === STEP.APPLYING}
                      />
                      <Icon name="class" size={14} style={{ color: "var(--accent)" }} />
                      <input
                        className="input input-sm"
                        value={c.name}
                        onChange={(e) => renameClass(ci, e.target.value)}
                        disabled={!c.selected || step === STEP.APPLYING}
                        style={{ flex: 1, fontWeight: 600 }}
                      />
                    </div>
                    {c.attributes.length > 0 && (
                      <div style={{ display: "grid", gap: 4, paddingLeft: 24 }}>
                        {c.attributes.map((a, ai) => (
                          <label key={ai} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, cursor: "pointer" }}>
                            <input
                              type="checkbox"
                              checked={a.selected}
                              onChange={() => toggleAttr(ci, ai)}
                              disabled={!c.selected || step === STEP.APPLYING}
                            />
                            <span className="text-muted">
                              {a.name} : {a.type}
                              {a.required ? " *" : ""}
                            </span>
                          </label>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>

              {relations.length > 0 && (
                <div style={{ display: "grid", gap: "var(--sp-2)" }}>
                  <h4 className="section-title">Relaciones</h4>
                  {relations.map((r, ri) => {
                    const bothSelected = selectedClassNames.has(r.from_class) && selectedClassNames.has(r.to_class);
                    return (
                      <label
                        key={ri}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 6,
                          fontSize: 12,
                          padding: "var(--sp-2) var(--sp-3)",
                          borderRadius: "var(--radius)",
                          background: "var(--surface-2)",
                          opacity: bothSelected && r.selected ? 1 : 0.5,
                          cursor: bothSelected ? "pointer" : "not-allowed",
                        }}
                      >
                        <input
                          type="checkbox"
                          checked={r.selected}
                          disabled={!bothSelected || step === STEP.APPLYING}
                          onChange={() => toggleRelation(ri)}
                        />
                        <span>
                          {r.from_class} → {r.to_class} · {r.type}
                        </span>
                        {!bothSelected && (
                          <span className="text-subtle">(se excluye una clase)</span>
                        )}
                      </label>
                    );
                  })}
                </div>
              )}

              <div style={{ display: "flex", gap: "var(--sp-2)", justifyContent: "flex-end" }}>
                <button className="btn" onClick={onClose} disabled={step === STEP.APPLYING}>
                  Cancelar
                </button>
                <button
                  className="btn btn-primary"
                  onClick={handleConfirm}
                  disabled={totalSelectedClasses === 0 || step === STEP.APPLYING}
                >
                  <Icon name={step === STEP.APPLYING ? "loader" : "check"} className={step === STEP.APPLYING ? "spinning" : ""} />
                  {step === STEP.APPLYING ? "Creando…" : `Crear diagrama (${totalSelectedClasses} clase${totalSelectedClasses === 1 ? "" : "s"})`}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
