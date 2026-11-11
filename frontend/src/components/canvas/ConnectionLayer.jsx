// src/components/canvas/ConnectionLayer.jsx
//
// Dibuja las relaciones UML entre clases como una capa SVG superpuesta al
// lienzo. Lee la posición de cada clase directo del DOM (no de `classes`)
// porque durante un drag/resize el estado de posición vive localmente en
// cada ClassCard hasta que se suelta el mouse.

import { useEffect, useMemo, useState } from "react";
import { getAnchorForClassSide, getClassRectById, inferClosestSide } from "./utils/geometry";

// Negro en el tema claro y claro en el oscuro (ver --relation-line en
// theme.css). La relación seleccionada se resalta en ámbar.
const DEFAULT_COLOR = "var(--relation-line)";
const SELECTED_COLOR = "#e0902a";

export default function ConnectionLayer({
  classes,
  tempLink = null,
  relations = [],
  strokeColor = DEFAULT_COLOR,
  strokeWidth = 1.4,
  camera,
  selectedRelId = null,
  onSelectRelation,
  onUpdateRelation,
}) {
  const [viewport, setViewport] = useState(() => ({
    w: document.documentElement.clientWidth,
    h: document.documentElement.clientHeight,
  }));

  useEffect(() => {
    const onResize = () => {
      setViewport({
        w: document.documentElement.clientWidth,
        h: document.documentElement.clientHeight,
      });
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  // Las líneas leen la posición de cada clase directo del DOM
  // (getAnchorForClassSide → getBoundingClientRect), así que mientras se
  // arrastra o redimensiona una clase no alcanza con que cambien `classes`
  // o `camera`: hay que forzar un re-render en cada frame de movimiento
  // para que la relación siga a la tabla en vivo, no recién al soltar.
  const [geometryTick, forceTick] = useState(0);
  useEffect(() => {
    let raf = null;
    const onGeometryChange = () => {
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = null;
        forceTick((t) => t + 1);
      });
    };
    window.addEventListener("diagram:geometry-change", onGeometryChange);
    return () => {
      window.removeEventListener("diagram:geometry-change", onGeometryChange);
      if (raf) cancelAnimationFrame(raf);
    };
  }, []);

  // El primer cálculo de relationSegments corre en el mismo commit de React
  // en que se montan las ClassCard, ANTES de que el navegador termine de
  // pintarlas -- getAnchorForClassSide lee getBoundingClientRect() del DOM
  // real, así que ese primer cálculo puede leer rects todavía sin asentar
  // (o vacíos) y descartar todas las relaciones. Sin este recálculo, las
  // líneas quedaban invisibles hasta que alguien arrastraba o
  // redimensionaba una clase (lo único que hasta ahora disparaba
  // diagram:geometry-change).
  useEffect(() => {
    const raf = requestAnimationFrame(() => forceTick((t) => t + 1));
    return () => cancelAnimationFrame(raf);
  }, [relations, classes]);

  // Arrastre de los extremos de la relación seleccionada: en vez de tener
  // que ir al panel a elegir "Sale por/Llega por" en un <select>, se puede
  // agarrar directo la puntita de la línea en el lienzo y soltarla más
  // cerca de otro lado de la clase (arriba/abajo/izquierda/derecha) -- el
  // mismo repertorio de anclajes que ya soportaba el panel, solo que ahora
  // también se elige arrastrando.
  const [dragEndpoint, setDragEndpoint] = useState(null); // { relationId, end, classId, point }

  useEffect(() => {
    if (!dragEndpoint) return;

    const onMove = (e) => {
      setDragEndpoint((prev) => (prev ? { ...prev, point: { x: e.clientX, y: e.clientY } } : prev));
    };
    const onUp = (e) => {
      const { relationId, end, classId } = dragEndpoint;
      const side = inferClosestSide(classId, { x: e.clientX, y: e.clientY });
      const patchKey = end === "src" ? "src_anchor" : "dst_anchor";
      // El resultado real (la línea recalculada desde `relations`) llega
      // por el estado que actualiza el padre al resolverse; acá solo hace
      // falta no dejar la promesa sin atender si el PATCH falla.
      Promise.resolve(onUpdateRelation?.(relationId, { [patchKey]: side })).catch(() => {
        alert("No se pudo mover la línea");
      });
      setDragEndpoint(null);
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [dragEndpoint, onUpdateRelation]);

  const startEndpointDrag = (relationId, end, classId, e) => {
    e.stopPropagation();
    e.preventDefault();
    setDragEndpoint({ relationId, end, classId, point: { x: e.clientX, y: e.clientY } });
  };

  /** Normaliza el tipo de relación (si no viene o es inválido → ASSOCIATION) */
  const normalizeType = (t) => {
    switch ((t || "").toUpperCase()) {
      case "ASSOCIATION":
      case "INHERITANCE":
      case "GENERALIZATION":
      case "AGGREGATION":
      case "COMPOSITION":
      case "DEPENDENCY":
      case "REALIZATION":
        return t.toUpperCase();
      default:
        return "ASSOCIATION";
    }
  };

  const norm = (r) => ({
    id: r.id ?? `${r.from_class ?? r.origen_id}->${r.to_class ?? r.destino_id}`,
    fromId: r.from_class ?? r.origen_id,
    toId: r.to_class ?? r.destino_id,
    type: normalizeType(r.type ?? r.tipo),
    srcA: r.src_anchor || "right",
    dstA: r.dst_anchor || "left",
    srcMin: r.src_mult_min ?? r.mult_origen_min ?? 1,
    srcMax: r.src_mult_max ?? r.mult_origen_max ?? null,
    dstMin: r.dst_mult_min ?? r.mult_destino_min ?? 1,
    dstMax: r.dst_mult_max ?? r.mult_destino_max ?? null,
    label: r.label ?? r.etiqueta ?? null,
    esClaseAsociacion: r.es_clase_asociacion ?? false,
    // UML 2.5: nombre de rol y navegabilidad de cada extremo
    srcRole: r.src_role ?? r.rol_origen ?? null,
    dstRole: r.dst_role ?? r.rol_destino ?? null,
    srcNav: r.src_navigable ?? r.navegable_origen ?? false,
    dstNav: r.dst_navigable ?? r.navegable_destino ?? false,
  });

  // UML: "1" en vez de "1..1" y "*" en vez de "0..*".
  const fmtMult = (min, max) => {
    const lo = min ?? 0;
    if (max == null) return lo === 0 ? "*" : `${lo}..*`;
    return lo === max ? `${lo}` : `${lo}..${max}`;
  };

  // El nombre de rol va del otro lado de la línea que la multiplicidad.
  const roleOffset = (side) => {
    switch (side) {
      case "left": return { dx: -10, dy: 13, anchor: "end" };
      case "right": return { dx: 10, dy: 13, anchor: "start" };
      case "top": return { dx: 8, dy: -20, anchor: "start" };
      case "bottom": return { dx: 8, dy: 27, anchor: "start" };
      default: return { dx: 8, dy: 13, anchor: "start" };
    }
  };

  const labelOffset = (side) => {
    switch (side) {
      case "left": return { dx: -10, dy: -5, anchor: "end" };
      case "right": return { dx: 10, dy: -5, anchor: "start" };
      case "top": return { dx: 0, dy: -8, anchor: "middle" };
      case "bottom": return { dx: 0, dy: 15, anchor: "middle" };
      default: return { dx: 8, dy: -5, anchor: "start" };
    }
  };

  const relationSegments = useMemo(() => {
    const normalized = relations.map(norm).filter((r) => r.fromId && r.toId);

    // UML 2.5: una clase de asociacion se dibuja con la asociacion normal
    // (solida) entre las dos clases originales, y una tercera linea
    // punteada que sale del punto medio de esa asociacion hacia la clase
    // intermedia -- no como dos lineas punteadas en serie (A--interm--B),
    // que es como las guarda la base de datos (ver convertToAssociationClass
    // en Diagram.jsx: siempre son 2 relaciones separadas, nunca 3).
    //
    // Detectar la intermedia NO alcanza con "participa en exactamente 2
    // relaciones marcadas": una clase que participa de DOS clases de
    // asociacion distintas (ej. "Venta" conectada a la vez con
    // Detalle_Venta y con Detalle_Devolucion) tambien junta 2 relaciones
    // marcadas, una por cada par, sin ser intermedia de ninguna. El
    // criterio real es que la intermedia NO TIENE NINGUNA otra relacion:
    // sus UNICAS relaciones en todo el diagrama son esas 2 marcadas.
    const assocFlagged = normalized.filter((r) => r.esClaseAsociacion);
    const allByClass = new Map(); // classId -> cantidad total de relaciones (cualquier tipo)
    for (const r of normalized) {
      for (const side of [r.fromId, r.toId]) {
        allByClass.set(side, (allByClass.get(side) || 0) + 1);
      }
    }
    const byIntermedia = new Map(); // classId candidato a intermedia -> [relacion,...]
    for (const r of assocFlagged) {
      for (const side of [r.fromId, r.toId]) {
        if (!byIntermedia.has(side)) byIntermedia.set(side, []);
        byIntermedia.get(side).push(r);
      }
    }

    const syntheticIds = new Set(); // relaciones ya absorbidas en un patron de T, no dibujar sueltas
    const tSegments = [];
    for (const [classId, rels] of byIntermedia) {
      if (rels.length !== 2) continue;
      // Si esta clase tiene mas relaciones en total que las 2 marcadas que
      // junto aca, no es la intermedia -- es una de las clases "reales"
      // que participa en multiples clases de asociacion.
      if ((allByClass.get(classId) || 0) !== 2) continue;
      const [r1, r2] = rels;
      if (r1.id === r2.id) continue;
      // classId tiene que ser el extremo COMUN de ambas relaciones, y las
      // otras dos puntas (las clases "reales") tienen que ser distintas
      // entre si -- si no, no es el patron en T (ej. dos relaciones que
      // casualmente comparten esClaseAsociacion pero no la misma intermedia).
      const other1 = r1.fromId === classId ? r1.toId : r1.fromId;
      const other2 = r2.fromId === classId ? r2.toId : r2.fromId;
      if (!other1 || !other2 || other1 === other2 || other1 === classId || other2 === classId) continue;
      if (syntheticIds.has(r1.id) || syntheticIds.has(r2.id)) continue;

      // Centro aproximado de cada clase (su rect en pantalla), para elegir
      // de que lado sale cada punta de la linea solida A-B segun hacia
      // donde esta la otra clase realmente -- fijar "right"/"left" se veia
      // mal cuando las clases quedan una arriba de la otra en vez de lado
      // a lado.
      const rectA = getClassRectById(other1);
      const rectB = getClassRectById(other2);
      if (!rectA || !rectB) continue;
      const centerA = { x: (rectA.left + rectA.right) / 2, y: (rectA.top + rectA.bottom) / 2 };
      const centerB = { x: (rectB.left + rectB.right) / 2, y: (rectB.top + rectB.bottom) / 2 };

      const aAnchor = getAnchorForClassSide(other1, inferClosestSide(other1, centerB));
      const bAnchor = getAnchorForClassSide(other2, inferClosestSide(other2, centerA));
      if (!aAnchor || !bAnchor) continue;

      const mid = { x: (aAnchor.x + bAnchor.x) / 2, y: (aAnchor.y + bAnchor.y) / 2 };
      const midAnchor = getAnchorForClassSide(classId, inferClosestSide(classId, mid));
      if (!midAnchor) continue;

      syntheticIds.add(r1.id);
      syntheticIds.add(r2.id);

      // Segmento solido A-B: toma label/multiplicidad combinados de las
      // dos relaciones originales (son las mismas que el usuario cargo al
      // convertir la relacion a clase de asociacion).
      tSegments.push({
        ...r1,
        id: `${r1.id}+${r2.id}`,
        fromId: other1,
        toId: other2,
        a: aAnchor,
        b: bAnchor,
        srcA: "right",
        dstA: "left",
        esClaseAsociacion: false,
        isAssociationClassSolid: true,
        recursive: false,
      });
      // Tercer brazo: punteado, sin flecha, del punto medio a la intermedia.
      tSegments.push({
        id: `${r1.id}+${r2.id}--link`,
        fromId: classId,
        toId: classId,
        type: "ASSOCIATION",
        a: mid,
        b: midAnchor,
        srcA: "right",
        dstA: "right",
        srcMin: null, srcMax: null, dstMin: null, dstMax: null,
        label: null,
        esClaseAsociacion: true,
        isAssociationClassLink: true,
        recursive: false,
      });
    }

    const segs = [...tSegments];
    for (const r of normalized) {
      if (syntheticIds.has(r.id)) continue;
      const a = getAnchorForClassSide(r.fromId, r.srcA);
      const b = getAnchorForClassSide(r.toId, r.dstA);
      if (!a || !b) continue;
      segs.push({ ...r, a, b, recursive: r.fromId === r.toId });
    }
    return segs;
  }, [relations, classes, camera, geometryTick]);

  const tempSegment = useMemo(() => {
    if (!tempLink) return null;
    const from = getAnchorForClassSide(tempLink.fromId, tempLink.fromSide || "right");
    const to = tempLink.cursor || null;
    if (!from || !to) return null;
    return { a: from, b: to, type: "ASSOCIATION" };
  }, [tempLink, classes, camera]);

  /** Curva de una relación recursiva (una clase relacionada consigo misma). */
  const recursivePath = (seg) => {
    const offset = 200;
    switch (seg.srcA) {
      case "top":
        return `M ${seg.a.x} ${seg.a.y} C ${seg.a.x} ${seg.a.y - offset}, ${seg.b.x} ${seg.b.y - offset}, ${seg.b.x} ${seg.b.y}`;
      case "bottom":
        return `M ${seg.a.x} ${seg.a.y} C ${seg.a.x} ${seg.a.y + offset}, ${seg.b.x} ${seg.b.y + offset}, ${seg.b.x} ${seg.b.y}`;
      case "left":
        return `M ${seg.a.x} ${seg.a.y} C ${seg.a.x - offset} ${seg.a.y}, ${seg.b.x - offset} ${seg.b.y}, ${seg.b.x} ${seg.b.y}`;
      default: // right
        return `M ${seg.a.x} ${seg.a.y} C ${seg.a.x + offset} ${seg.a.y}, ${seg.b.x + offset} ${seg.b.y}, ${seg.b.x} ${seg.b.y}`;
    }
  };

  return (
    <svg
      width={viewport.w}
      height={viewport.h}
      style={{
        position: "fixed",
        inset: 0,
        pointerEvents: "none",
        overflow: "visible",
        // Por encima de las tarjetas, pero por debajo de los paneles y de
        // los diálogos: al estar en position fixed, un z-index alto hacía
        // que las líneas se dibujaran encima de toda la interfaz.
        zIndex: "var(--z-connections)",
      }}
    >
      <defs>
        {/* Sombra suave para la relación seleccionada, igual que el halo
            que ya usan las clases seleccionadas en el lienzo.
            userSpaceOnUse (no objectBoundingBox, el default) porque una
            línea horizontal o vertical tiene alto o ancho 0: con
            objectBoundingBox el área de filtro se calcula como porcentaje
            de esa caja y colapsa a 0px en ese eje, recortando toda la
            línea en vez de solo agregarle sombra. */}
        <filter id="rel-glow" filterUnits="userSpaceOnUse" x="-20" y="-20" width="10000" height="10000">
          <feDropShadow dx="0" dy="0" stdDeviation="2" floodColor={SELECTED_COLOR} floodOpacity="0.55" />
        </filter>

        {/* Marcadores por color: uno para el trazo normal y otro para la
            relación seleccionada, con su propio color de acento. */}
        {[
          { suffix: "", color: strokeColor },
          { suffix: "-sel", color: SELECTED_COLOR },
        ].map(({ suffix, color }) => (
          <g key={suffix || "default"}>
            <marker id={`arrow-normal${suffix}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0.5 L 9 5 L 0 9.5 z" fill={color} />
            </marker>
            <marker id={`arrow-hollow${suffix}`} viewBox="0 0 22 16" refX="20" refY="8" markerWidth="10" markerHeight="7.5" orient="auto-start-reverse">
              <path d="M 20 8 L 1 1 L 1 15 z" fill="var(--surface-1)" stroke={color} strokeWidth="1.6" strokeLinejoin="round" />
            </marker>
            <marker id={`diamond-hollow${suffix}`} viewBox="0 0 24 14" refX="22" refY="7" markerWidth="11" markerHeight="6.5" orient="auto-start-reverse">
              <path d="M 1 7 L 12 1 L 23 7 L 12 13 z" fill="var(--surface-1)" stroke={color} strokeWidth="1.6" strokeLinejoin="round" />
            </marker>
            <marker id={`diamond-filled${suffix}`} viewBox="0 0 24 14" refX="22" refY="7" markerWidth="11" markerHeight="6.5" orient="auto-start-reverse">
              <path d="M 1 7 L 12 1 L 23 7 L 12 13 z" fill={color} />
            </marker>
            {/* Flecha abierta (UML 2.5): dependencia y navegabilidad. */}
            <marker id={`arrow-open${suffix}`} viewBox="0 0 12 12" refX="11" refY="6" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
              <path d="M 1 1 L 11 6 L 1 11" fill="none" stroke={color} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
            </marker>
          </g>
        ))}
      </defs>

      {relationSegments.map((seg) => {
        const isSelected = seg.id === selectedRelId;
        const color = isSelected ? SELECTED_COLOR : strokeColor;
        const suffix = isSelected ? "-sel" : "";

        // Mientras se arrastra uno de los extremos de ESTA relación, ese
        // punto sigue al mouse en vivo en vez de quedar clavado en el
        // anclaje anterior -- si no, el handle se ve "pegado" a la clase
        // hasta soltar, sin dar ninguna pista de hacia dónde se está
        // moviendo la línea.
        const draggingSrc = dragEndpoint?.relationId === seg.id && dragEndpoint.end === "src";
        const draggingDst = dragEndpoint?.relationId === seg.id && dragEndpoint.end === "dst";
        const a = draggingSrc ? dragEndpoint.point : seg.a;
        const b = draggingDst ? dragEndpoint.point : seg.b;

        const so = labelOffset(seg.srcA);
        const dof = labelOffset(seg.dstA);
        const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };

        const lineProps = {
          stroke: color,
          strokeWidth: isSelected ? strokeWidth + 1 : strokeWidth,
          strokeLinecap: "round",
          filter: isSelected ? "url(#rel-glow)" : undefined,
        };
        let markerEnd = null;
        let markerStart = null;

        switch (seg.type) {
          case "ASSOCIATION":
            markerEnd = null;
            // UML: la linea que une una clase de asociacion (muchos-a-
            // muchos con atributos propios) con las clases originales se
            // dibuja punteada, para distinguirla de una asociacion comun.
            if (seg.esClaseAsociacion) lineProps.strokeDasharray = "6,4";
            break;
          case "INHERITANCE":
          case "GENERALIZATION":
            markerEnd = `url(#arrow-hollow${suffix})`;
            break;
          case "AGGREGATION":
            markerEnd = `url(#diamond-hollow${suffix})`;
            break;
          case "COMPOSITION":
            markerEnd = `url(#diamond-filled${suffix})`;
            break;
          case "DEPENDENCY":
            // UML 2.5: punteada con flecha ABIERTA hacia el proveedor.
            lineProps.strokeDasharray = "6,4";
            markerEnd = `url(#arrow-open${suffix})`;
            break;
          case "REALIZATION":
            // UML 2.5: punteada con triángulo hueco hacia la interfaz.
            lineProps.strokeDasharray = "6,4";
            markerEnd = `url(#arrow-hollow${suffix})`;
            break;
          default:
            markerEnd = null;
        }

        // Navegabilidad (UML 2.5): flecha abierta en el extremo navegable.
        // En agregación/composición el rombo ya ocupa el extremo destino.
        const esAsociacion = ["ASSOCIATION", "AGGREGATION", "COMPOSITION"].includes(seg.type);
        if (esAsociacion && !seg.isAssociationClassLink) {
          if (seg.dstNav && !markerEnd) markerEnd = `url(#arrow-open${suffix})`;
          if (seg.srcNav) markerStart = `url(#arrow-open${suffix})`;
        }

        const labelStyle = {
          userSelect: "none",
          fontWeight: isSelected ? 600 : 400,
          fill: isSelected ? SELECTED_COLOR : "var(--text)",
        };

        // UML: herencia y dependencia no llevan multiplicidad (un
        // subtipo es exactamente uno del supertipo, y una dependencia es
        // un uso puntual, no una cardinalidad) -- mismo criterio que ya
        // aplica RelationInspector para ocultar esos campos en el panel.
        const sinMultiplicidad = ["INHERITANCE", "GENERALIZATION", "DEPENDENCY", "REALIZATION"].includes(seg.type) || seg.isAssociationClassLink;
        const ro = roleOffset(seg.srcA);
        const rd = roleOffset(seg.dstA);

        const labels = (
          <>
            {!sinMultiplicidad && (
              <>
                <text x={a.x + so.dx} y={a.y + so.dy} fontSize="10" textAnchor={so.anchor} style={labelStyle}>
                  {fmtMult(seg.srcMin, seg.srcMax)}
                </text>
                <text x={b.x + dof.dx} y={b.y + dof.dy} fontSize="10" textAnchor={dof.anchor} style={labelStyle}>
                  {fmtMult(seg.dstMin, seg.dstMax)}
                </text>
                {seg.srcRole && (
                  <text x={a.x + ro.dx} y={a.y + ro.dy} fontSize="10" fontStyle="italic" textAnchor={ro.anchor} style={labelStyle}>
                    {seg.srcRole}
                  </text>
                )}
                {seg.dstRole && (
                  <text x={b.x + rd.dx} y={b.y + rd.dy} fontSize="10" fontStyle="italic" textAnchor={rd.anchor} style={labelStyle}>
                    {seg.dstRole}
                  </text>
                )}
              </>
            )}
            {seg.label && (
              <text x={mid.x} y={mid.y - 6} fontSize="10" textAnchor="middle" style={labelStyle}>
                {seg.label}
              </text>
            )}
          </>
        );

        // Los segmentos sinteticos de la geometria en T (la linea solida
        // A-B reconstruida y su tercer brazo punteado) no son una fila
        // real en la base de datos -- su "id" es compuesto
        // ("rel1+rel2"/"rel1+rel2--link") y no existe como relacion
        // propia, asi que no se puede seleccionar/editar/arrastrar como
        // si fuera una. El click pasa de largo hasta lo que esta debajo.
        const hitProps = {
          stroke: "transparent",
          strokeWidth: Math.max(16, strokeWidth + 10),
          style: {
            pointerEvents: seg.isAssociationClassLink || seg.isAssociationClassSolid ? "none" : "auto",
            cursor: onSelectRelation ? "pointer" : "default",
          },
          onClick: () => onSelectRelation?.(seg.id),
        };

        // Handles para arrastrar cada extremo a otro lado de su clase: solo
        // en la relación seleccionada y solo cuando no es recursiva (una
        // clase consigo misma ya usa un par de anclajes fijos por diseño,
        // ver getAnchorsForRelation). pointerEvents "auto" porque el resto
        // del SVG lo tiene en "none" para dejar pasar los clicks al Sheet.
        const endpointHandles =
          isSelected && !seg.recursive && !seg.isAssociationClassLink && !seg.isAssociationClassSolid && onUpdateRelation ? (
            <>
              <circle
                cx={a.x} cy={a.y} r={7}
                fill="var(--surface-1)" stroke={SELECTED_COLOR} strokeWidth={2}
                style={{ pointerEvents: "auto", cursor: "grab" }}
                onMouseDown={(e) => startEndpointDrag(seg.id, "src", seg.fromId, e)}
              >
                <title>Arrastrá para cambiar por dónde sale la línea</title>
              </circle>
              <circle
                cx={b.x} cy={b.y} r={7}
                fill="var(--surface-1)" stroke={SELECTED_COLOR} strokeWidth={2}
                style={{ pointerEvents: "auto", cursor: "grab" }}
                onMouseDown={(e) => startEndpointDrag(seg.id, "dst", seg.toId, e)}
              >
                <title>Arrastrá para cambiar por dónde llega la línea</title>
              </circle>
            </>
          ) : null;

        if (seg.recursive) {
          const d = recursivePath(seg);
          return (
            <g key={seg.id}>
              <path d={d} {...lineProps} fill="none" markerEnd={markerEnd} markerStart={markerStart} />
              <path d={d} {...hitProps} fill="none" />
              {labels}
            </g>
          );
        }

        return (
          <g key={seg.id}>
            <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} {...lineProps} markerEnd={markerEnd} markerStart={markerStart} />
            <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} {...hitProps} />
            {labels}
            {endpointHandles}
          </g>
        );
      })}

      {tempSegment && (
        <line
          x1={tempSegment.a.x} y1={tempSegment.a.y}
          x2={tempSegment.b.x} y2={tempSegment.b.y}
          stroke={strokeColor}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          markerEnd="url(#arrow-normal)"
          opacity="0.7"
        />
      )}
    </svg>
  );
}
