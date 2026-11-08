// frontend/src/pages/Diagram.jsx

import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

// ===== utilidades geométricas para canvas =====
import { hitTestClasses, inferClosestSide } from "../components/canvas/utils/geometry";

// ===== estado global (auth) =====
import useAuth from "../store/auth";
import useUndo from "../store/undo";

// ===== hooks personalizados (lógica de negocio) =====
import useTheme from "../hooks/useTheme";
import useDiagram from "../hooks/useDiagram";
import useClassesAndDetails from "../hooks/useClassesAndDetails";
import useRelations from "../hooks/useRelations";
import useExportDiagram from "../hooks/useExport";
import useDiagramLocks from "../hooks/useLocks";
import useLiveCursors from "../hooks/useLiveCursors";

// ===== componentes de UI =====
import Sheet from "../components/canvas/Sheet";
import ClassCard from "../components/canvas/ClassCard";
import ConnectionLayer from "../components/canvas/ConnectionLayer";
import Inspector from "../components/panels/Inspector";
import RelationInspector from "../components/panels/RelationInspector";
import ChatPanel from "../components/panels/ChatPanel";
import CollaboratorsModal from "../components/panels/CollaboratorsModal";
import AssociationClassModal from "../components/panels/AssociationClassModal";
import HelpGuide from "../components/common/HelpGuide";
import Icon from "../components/common/Icon";
import { exportXmi, importXmi } from "../api/xmi";
import { deleteRelation as apiDeleteRelation } from "../api/relations";

// ===== layout =====
import HeaderBar from "../components/layout/HeaderBar";
import LeftPanel from "../components/layout/LeftPanel";

const HELP_SEEN_KEY = "uml.help.seen";

export default function DiagramDashboard() {
  const { id } = useParams();
  const nav = useNavigate();

  const logout = useAuth((s) => s.logout);
  const email = useAuth((s) => s.email);

  const { theme, toggleTheme } = useTheme();
  const { diagram, loading, err } = useDiagram(id);

  const [linking, setLinking] = useState(null);
  const [camera, setCamera] = useState({ x: 0, y: 0, z: 1 });
  const [showHelp, setShowHelp] = useState(false);
  const [showCollaborators, setShowCollaborators] = useState(false);
  const [aviso, setAviso] = useState(null); // mensaje flotante de "deshecho"
  const [associationCandidate, setAssociationCandidate] = useState(null); // relación M:N que puede convertirse en clase de asociación

  const undoLast = useUndo((s) => s.undoLast);
  const undoCount = useUndo((s) => s.stack.length);
  const clearUndo = useUndo((s) => s.clear);

  const { exportDiagram, loading: exporting } = useExportDiagram();
  const [exportingXmi, setExportingXmi] = useState(false);
  const [importingXmi, setImportingXmi] = useState(false);

  const handleExportXmi = async () => {
    setExportingXmi(true);
    try {
      await exportXmi(diagram.id, diagram.title);
    } catch (err) {
      setAviso({ tipo: "error", texto: err?.response?.data?.detail || "No se pudo exportar el XMI" });
    } finally {
      setExportingXmi(false);
    }
  };

  const handleImportXmiFile = async (file) => {
    if (!file) return;
    setImportingXmi(true);
    try {
      const s = await importXmi(diagram.id, file);
      const partes = [
        s.classes_created.length ? `${s.classes_created.length} clase(s)` : null,
        s.attributes_created ? `${s.attributes_created} atributo(s)` : null,
        s.methods_created ? `${s.methods_created} método(s)` : null,
        s.relations_created ? `${s.relations_created} relación(es)` : null,
      ].filter(Boolean);
      const omitidas = s.classes_skipped.length ? ` (${s.classes_skipped.length} clase(s) ya existían)` : "";
      setAviso({
        tipo: "ok",
        texto: partes.length
          ? `Importado desde XMI: ${partes.join(", ")}${omitidas}.`
          : `No se importó nada nuevo${omitidas}.`,
      });
    } catch (err) {
      setAviso({ tipo: "error", texto: err?.response?.data?.detail || "No se pudo importar el archivo XMI" });
    } finally {
      setImportingXmi(false);
    }
  };

  const {
    relations,
    selectedRelId, setSelectedRelId,
    selectedRelation: selectedRel,
    createRelation, updateRelation, deleteRelation,
  } = useRelations(diagram);

  const {
    classes,
    selectedId, setSelectedId, selected,
    detailsByClass,
    insertMode, setInsertMode,
    insertName, setInsertName,
    fetchDetails,
    handleCanvasClick,
    handleDragEnd, handleResizeEnd,
    handleDelete,
    addAttr, patchAttr, removeAttr,
    addMeth, patchMeth, removeMeth,
    createAssociationClass,
  } = useClassesAndDetails(diagram);

  // =====================================================
  // Cursores en vivo de los demás colaboradores (estilo Miro/Figma).
  // =====================================================
  const { cursors: remoteCursors, reportCursor } = useLiveCursors(diagram?.id);

  // =====================================================
  // Exclusión mutua: al seleccionar una clase se pide su lock; al
  // deseleccionarla (o cambiar de selección) se suelta. El backend es quien
  // decide si el lock se otorga o no.
  // =====================================================
  const { lockClass, unlockClass, isLockedByOther, lockOwner } = useDiagramLocks(
    diagram?.id,
    (classId, lockedBy) => {
      const clase = classes.find((c) => c.id === classId);
      setAviso({
        tipo: "error",
        texto: `${clase?.name ?? "Esa clase"} la está editando ${lockedBy || "otra persona"} ahora mismo.`,
      });
      // El backend nunca me dio el lock: si igual quedó seleccionada acá,
      // deselecciono para no mostrar un editor sobre algo que no puedo tocar.
      setSelectedId((cur) => (cur === classId ? null : cur));
    }
  );

  const lockedClassRef = useRef(null);
  useEffect(() => {
    if (lockedClassRef.current && lockedClassRef.current !== selectedId) {
      unlockClass(lockedClassRef.current);
    }
    if (selectedId) lockClass(selectedId);
    lockedClassRef.current = selectedId;
  }, [selectedId, lockClass, unlockClass]);

  // Al salir del diagrama (desmontar), soltar el lock que haya quedado.
  useEffect(() => {
    return () => {
      if (lockedClassRef.current) unlockClass(lockedClassRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // La guía se abre sola la primera vez que alguien usa la herramienta.
  useEffect(() => {
    if (!localStorage.getItem(HELP_SEEN_KEY)) setShowHelp(true);
  }, []);

  const closeHelp = () => {
    localStorage.setItem(HELP_SEEN_KEY, "1");
    setShowHelp(false);
  };

  // La pila de deshacer es por diagrama: al salir no debe quedar nada que
  // pueda revertir cambios de otro diagrama.
  useEffect(() => clearUndo, [id, clearUndo]);

  // =====================================================
  // Deshacer (Ctrl+Z)
  // =====================================================
  const deshacer = async () => {
    const label = await undoLast();
    if (!label) {
      setAviso({ tipo: "vacio", texto: "No hay nada para deshacer" });
      return;
    }
    setAviso({ tipo: "ok", texto: `Se deshizo: ${label}` });
  };

  useEffect(() => {
    const onKeyDown = (e) => {
      const ctrl = e.ctrlKey || e.metaKey;
      if (!ctrl || e.key.toLowerCase() !== "z" || e.shiftKey) return;

      // Si el foco está en un campo de texto, dejamos que el navegador
      // deshaga lo que se escribió ahí en vez de revertir el diagrama.
      const el = document.activeElement;
      const escribiendo =
        el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable);
      if (escribiendo) return;

      e.preventDefault();
      deshacer();
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // El aviso se va solo
  useEffect(() => {
    if (!aviso) return;
    const t = setTimeout(() => setAviso(null), 2600);
    return () => clearTimeout(t);
  }, [aviso]);

  // =====================================================
  // Crear relación arrastrando entre clases
  // =====================================================
  useEffect(() => {
    if (!linking) return;

    const hitTestByDom = (pt) => {
      const stack = document.elementsFromPoint(pt.x, pt.y) || [];
      const el = stack.find((n) => n?.getAttribute && n.getAttribute("data-class-id"));
      return el ? el.getAttribute("data-class-id") || null : null;
    };

    const onMove = (e) => {
      setLinking((prev) => (prev ? { ...prev, cursor: { x: e.clientX, y: e.clientY } } : prev));
    };

    const onUp = async (e) => {
      const pt = { x: e.clientX, y: e.clientY };
      const toId = hitTestByDom(pt) || hitTestClasses(pt, classes);

      if (toId) {
        const dstSide = inferClosestSide(toId, pt);
        try {
          await createRelation({
            from_class: linking.fromId,
            to_class: toId,
            type: "ASSOCIATION",
            src_anchor: linking.fromSide,
            dst_anchor: dstSide,
          });
        } catch (err) {
          alert(err?.response?.data?.detail || "No se pudo crear la relación");
        }
      }
      setLinking(null);
    };

    window.addEventListener("mousemove", onMove, true);
    window.addEventListener("mouseup", onUp, true);
    return () => {
      window.removeEventListener("mousemove", onMove, true);
      window.removeEventListener("mouseup", onUp, true);
    };
  }, [linking, classes, diagram?.id]);

  // =====================================================
  // Carga / error
  // =====================================================
  if (loading) {
    return (
      <div style={{ height: "100vh", display: "grid", placeItems: "center", background: "var(--bg)", color: "var(--text)" }}>
        <div style={{ display: "flex", gap: "var(--sp-2)", alignItems: "center" }} className="text-muted">
          <Icon name="loader" className="spinning" />
          Cargando diagrama…
        </div>
      </div>
    );
  }

  if (err) {
    return (
      <div style={{ height: "100vh", display: "grid", placeItems: "center", background: "var(--bg)", color: "var(--text)" }}>
        <div className="card" style={{ display: "grid", gap: "var(--sp-3)", justifyItems: "center", maxWidth: 360, textAlign: "center" }}>
          <Icon name="warning" size={22} style={{ color: "var(--danger)" }} />
          <div style={{ fontWeight: 600 }}>No se pudo abrir el diagrama</div>
          <div className="text-muted" style={{ fontSize: 13 }}>{err}</div>
          <button className="btn btn-primary" onClick={() => nav("/")}>Volver a mis diagramas</button>
        </div>
      </div>
    );
  }

  if (!diagram) return null;

  // No atrapa el error acá: RelationInspector usa useAutoSave con esta
  // función, que necesita que la promesa rechace para poder mostrar el
  // estado "no se pudo guardar" en el panel en vez de un alert(). Acepta un
  // id explícito (lo usa ConnectionLayer al arrastrar el extremo de
  // CUALQUIER relación, no solo la seleccionada) y, si no se pasa, cae en
  // la relación actualmente seleccionada -- así RelationInspector la sigue
  // llamando igual que antes.
  const handleUpdateRelation = async (patch, relationId = selectedRel?.id) => {
    if (!relationId) return;
    const updated = await updateRelation(relationId, patch);

    // UML 2.5: una asociación muchos-a-muchos con atributos propios se
    // modela como una clase de asociación explícita, no solo como una
    // tabla intermedia invisible generada por Hibernate. Se ofrece la
    // conversión apenas ambos lados quedan en "*" sobre una asociación
    // simple entre dos clases distintas (self-relaciones recursivas ya
    // se resuelven distinto, no aplica acá).
    //
    // El backend devuelve esta respuesta con los nombres de campo en
    // español del ORM (origen_id/tipo/mult_origen_max), NO con los alias
    // en inglés que sí usa el body al crear/actualizar -- son shapes
    // distintos a propósito de este backend, no un typo.
    const esMuchosAMuchos =
      updated.tipo === "ASSOCIATION" &&
      (updated.mult_origen_max === "*" || updated.mult_origen_max === null) &&
      (updated.mult_destino_max === "*" || updated.mult_destino_max === null) &&
      updated.origen_id !== updated.destino_id;

    if (esMuchosAMuchos) {
      setAssociationCandidate(updated);
    }
  };

  const convertToAssociationClass = async (relation) => {
    const claseOrigen = classes.find((c) => c.id === relation.origen_id);
    const claseDestino = classes.find((c) => c.id === relation.destino_id);
    if (!claseOrigen || !claseDestino) return;

    try {
      const xGrid = Math.round((claseOrigen.x_grid + claseDestino.x_grid) / 2);
      const yGrid = Math.round((claseOrigen.y_grid + claseDestino.y_grid) / 2) + 4;

      const intermedia = await createAssociationClass({
        nameA: claseOrigen.name,
        nameB: claseDestino.name,
        xGrid, yGrid,
      });

      await createRelation({
        from_class: claseOrigen.id,
        to_class: intermedia.id,
        type: "ASSOCIATION",
        src_mult_min: 1, src_mult_max: 1,
        dst_mult_min: 0, dst_mult_max: "*",
        es_clase_asociacion: true,
      });
      await createRelation({
        from_class: intermedia.id,
        to_class: claseDestino.id,
        type: "ASSOCIATION",
        src_mult_min: 0, src_mult_max: "*",
        dst_mult_min: 1, dst_mult_max: 1,
        es_clase_asociacion: true,
      });

      // Se usa el DELETE directo (no el deleteRelation del hook) porque ese
      // ya pide su propia confirmación por diálogo, y acá el usuario ya
      // confirmó la conversión completa un paso antes.
      await apiDeleteRelation(relation.id);
      setSelectedRelId(null);
    } catch {
      alert("No se pudo crear la clase de asociación");
    } finally {
      setAssociationCandidate(null);
    }
  };

  const handleDeleteRelation = async () => {
    try {
      await deleteRelation(selectedRel.id);
      setSelectedRelId(null);
    } catch {
      alert("No se pudo eliminar la relación");
    }
  };

  // =====================================================
  // Render
  // =====================================================
  return (
    <div
      style={{
        display: "grid",
        gridTemplateRows: "var(--header-h) 1fr",
        height: "100vh",
        background: "var(--bg)",
        color: "var(--text)",
        overflow: "hidden",
      }}
    >
      <HeaderBar
        diagram={diagram}
        email={email}
        theme={theme}
        toggleTheme={toggleTheme}
        insertMode={insertMode}
        setInsertMode={setInsertMode}
        onBack={() => nav("/")}
        onLogout={() => { logout(); nav("/login", { replace: true }); }}
        onExport={() => exportDiagram(diagram.id)}
        exporting={exporting}
        onExportXmi={handleExportXmi}
        exportingXmi={exportingXmi}
        onImportXmiFile={handleImportXmiFile}
        importingXmi={importingXmi}
        onOpenHelp={() => setShowHelp(true)}
        onUndo={deshacer}
        canUndo={undoCount > 0}
        onOpenCollaborators={() => setShowCollaborators(true)}
      />

      <div style={{ display: "flex", minHeight: 0 }}>
        <LeftPanel
          classes={classes}
          relations={relations}
          selectedId={selectedId}
          selectedRelId={selectedRelId}
          onSelectClass={(cid) => {
            if (isLockedByOther(cid)) return;
            setSelectedId(cid);
            setSelectedRelId(null);
          }}
          onSelectRelation={(rid) => { setSelectedRelId(rid); setSelectedId(null); }}
        />

        {/* ---------------- Lienzo ---------------- */}
        <main style={{ position: "relative", flex: 1, minWidth: 0 }}>
          {/* Instrucción del modo insertar */}
          {insertMode && (
            <div
              style={{
                position: "absolute",
                top: "var(--sp-4)",
                left: "50%",
                transform: "translateX(-50%)",
                zIndex: "var(--z-banner)",
                display: "flex",
                alignItems: "center",
                gap: "var(--sp-3)",
                padding: "var(--sp-2) var(--sp-3)",
                borderRadius: "var(--radius)",
                background: "var(--surface-1)",
                border: "1px solid var(--accent)",
                boxShadow: "var(--shadow)",
              }}
            >
              <Icon name="info" size={15} style={{ color: "var(--accent)" }} />
              <span style={{ fontSize: 13 }}>Escribí el nombre y hacé clic en el lienzo:</span>
              <input
                className="input input-sm"
                style={{ width: 150 }}
                value={insertName}
                onChange={(e) => setInsertName(e.target.value)}
                placeholder="Ej: Cliente"
                autoFocus
              />
              <button className="btn btn-sm" onClick={() => setInsertMode(false)}>
                Cancelar
              </button>
            </div>
          )}

          {/* Estado vacío: qué hacer cuando el diagrama recién arranca */}
          {classes.length === 0 && !insertMode && (
            <div
              style={{
                position: "absolute",
                inset: 0,
                display: "grid",
                placeItems: "center",
                pointerEvents: "none",
                zIndex: "var(--z-banner)",
              }}
            >
              <div
                className="panel"
                style={{
                  pointerEvents: "auto",
                  padding: "var(--sp-5)",
                  maxWidth: 380,
                  textAlign: "center",
                  display: "grid",
                  gap: "var(--sp-3)",
                  justifyItems: "center",
                  boxShadow: "var(--shadow)",
                }}
              >
                <div
                  style={{
                    width: 44, height: 44, display: "grid", placeItems: "center",
                    borderRadius: "var(--radius)", background: "var(--accent-soft)", color: "var(--accent)",
                  }}
                >
                  <Icon name="class" size={20} />
                </div>
                <div style={{ fontWeight: 600 }}>Este diagrama está vacío</div>
                <div className="text-muted" style={{ fontSize: 13 }}>
                  Empezá creando tu primera clase. Podés hacerlo vos mismo o pedírselo
                  al asistente escribiendo o hablando.
                </div>
                <div style={{ display: "flex", gap: "var(--sp-2)" }}>
                  <button className="btn btn-primary" onClick={() => setInsertMode(true)}>
                    <Icon name="plus" />
                    Crear una clase
                  </button>
                  <button className="btn" onClick={() => setShowHelp(true)}>
                    <Icon name="help" />
                    Ver la guía
                  </button>
                </div>
              </div>
            </div>
          )}

          <Sheet
            onCanvasClick={handleCanvasClick}
            onEmptyClick={() => {
              setSelectedId(null);
              setSelectedRelId(null);
            }}
            onCameraChange={setCamera}
            onCursorMove={(x, y) => reportCursor(x, y, selected ? `editando ${selected.name}` : null)}
            remoteCursors={remoteCursors}
          >
            {classes.map((c) => (
              <ClassCard
                key={c.id}
                cls={c}
                selected={c.id === selectedId}
                onSelect={(cid) => {
                  if (isLockedByOther(cid)) return; // seleccionar no sirve de nada si no puedo editarla
                  setSelectedId(cid);
                  setSelectedRelId(null);
                }}
                onDragEnd={handleDragEnd}
                onResizeEnd={handleResizeEnd}
                details={detailsByClass[c.id]}
                alwaysShowDetails={true}
                showLinkPortsOnHover={true}
                forceShowPorts={!!linking && c.id !== linking?.fromId}
                onStartLink={(fromId, side, pt) => setLinking({ fromId, fromSide: side, cursor: pt })}
                lockedByOther={isLockedByOther(c.id) ? lockOwner(c.id) : null}
              />
            ))}
          </Sheet>

          <ConnectionLayer
            classes={classes}
            tempLink={linking ? { fromId: linking.fromId, fromSide: linking.fromSide, cursor: linking.cursor } : null}
            relations={relations}
            camera={camera}
            selectedRelId={selectedRelId}
            onSelectRelation={(rid) => { setSelectedRelId(rid); setSelectedId(null); }}
            onUpdateRelation={(relationId, patch) => handleUpdateRelation(patch, relationId)}
          />

          {/* Aviso de deshacer */}
          {aviso && (
            <div
              style={{
                position: "absolute",
                bottom: "var(--sp-4)",
                left: "50%",
                transform: "translateX(-50%)",
                zIndex: "var(--z-toast)",
                display: "flex",
                alignItems: "center",
                gap: "var(--sp-2)",
                padding: "var(--sp-2) var(--sp-4)",
                borderRadius: 999,
                background: "var(--surface-3)",
                border: "1px solid var(--border-strong)",
                boxShadow: "var(--shadow)",
                fontSize: 12,
              }}
            >
              <Icon
                name={aviso.tipo === "ok" ? "check" : aviso.tipo === "error" ? "warning" : "info"}
                size={14}
                style={{
                  color:
                    aviso.tipo === "ok" ? "var(--success)"
                    : aviso.tipo === "error" ? "var(--danger)"
                    : "var(--text-subtle)",
                }}
              />
              {aviso.texto}
            </div>
          )}

          <ChatPanel diagramId={diagram.id} myEmail={email} />
        </main>

        {/* ---------------- Panel derecho ---------------- */}
        {selectedRel ? (
          <RelationInspector
            relation={selectedRel}
            onUpdate={handleUpdateRelation}
            onDelete={handleDeleteRelation}
          />
        ) : (
          <Inspector
            selected={selected}
            details={selected ? detailsByClass[selected.id] : undefined}
            reloadDetails={() => selected && fetchDetails(selected.id)}
            onDeleteClass={() => selected && handleDelete(selected.id)}
            onAddAttr={(cid) => addAttr(cid)}
            onPatchAttr={(cid, aid, patch) => patchAttr(cid, aid, patch)}
            onRemoveAttr={(cid, aid) => removeAttr(cid, aid)}
            onAddMeth={(cid) => addMeth(cid)}
            onPatchMeth={(cid, mid, patch) => patchMeth(cid, mid, patch)}
            onRemoveMeth={(cid, mid) => removeMeth(cid, mid)}
          />
        )}
      </div>

      {showHelp && <HelpGuide onClose={closeHelp} />}
      {showCollaborators && (
        <CollaboratorsModal
          diagram={diagram}
          isOwner={diagram.owner_email === email}
          onClose={() => setShowCollaborators(false)}
        />
      )}
      {associationCandidate && (
        <AssociationClassModal
          origenNombre={associationCandidate.origen_nombre}
          destinoNombre={associationCandidate.destino_nombre}
          onCancel={() => setAssociationCandidate(null)}
          onConfirm={() => convertToAssociationClass(associationCandidate)}
        />
      )}
    </div>
  );
}
