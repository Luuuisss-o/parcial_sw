// src/hooks/useDiagram.js
// (Hook personalizado para cargar un diagrama desde la API, no cambia la lógica)
import { useEffect, useState } from "react";
import api from "../api/client";

export default function useDiagram(diagramId) {
  // 🔹 Estado que guarda el diagrama cargado desde la API
  const [diagram, setDiagram] = useState(null);

  // 🔹 Estado para indicar si está cargando (true al inicio)
  const [loading, setLoading] = useState(true);

  // 🔹 Estado para manejar mensajes de error
  const [err, setErr] = useState("");

  // 🔹 Cambia para volver a pedir el diagrama (p. ej. cambió mi rol)
  const [reloadKey, setReloadKey] = useState(0);
  const reload = () => setReloadKey((k) => k + 1);

  // 🔹 Efecto: se ejecuta cuando cambia el `diagramId`
  useEffect(() => {
    let alive = true; // bandera para evitar actualizar estado si el componente ya se desmontó

    (async () => {
      // Al recargar no se muestra el "cargando" de pantalla completa.
      if (reloadKey === 0) setLoading(true);
      setErr("");         // limpia errores previos

      try {
        // 📡 Llamada a la API: obtiene el diagrama por ID
        const { data } = await api.get(`/diagrams/${diagramId}`);

        // Si el componente ya se desmontó, no actualizar estados
        if (!alive) return;

        setDiagram(data); // guarda el diagrama en el estado
      } catch (e) {
        if (!alive) return;
        // Maneja errores: usa el detalle de la API o un mensaje genérico
        setErr(e?.response?.data?.detail || "No se pudo cargar el diagrama");
      } finally {
        if (!alive) return;
        setLoading(false); // desactiva el indicador de carga
      }
    })();

    // 🔹 Cleanup: cuando el componente se desmonta, cambia `alive` a false
    return () => { alive = false; };
  }, [diagramId, reloadKey]); // si cambia el ID (o se pide recargar), vuelve a cargarlo

  // 🔹 Devuelve los valores útiles para el componente que use este hook
  return { diagram, loading, err, reload };
}
