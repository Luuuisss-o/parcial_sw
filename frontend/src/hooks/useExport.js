import { useState } from "react";

export default function useExportDiagram() {
  const [loading, setLoading] = useState(false);

  async function exportDiagram(diagramId) {
    setLoading(true);
    try {
      const urlApi = `${import.meta.env.VITE_API_URL}/diagrams/${diagramId}/export-download`;
      console.log("📤 Exportando diagrama:", diagramId, "=>", urlApi);

      const res = await fetch(urlApi, { method: "POST" });

      console.log("📥 Respuesta:", res.status, res.statusText);

      if (!res.ok) {
        let errorMsg = "";
        try {
          const text = await res.text();
          errorMsg = text || res.statusText;
        } catch (e) {
          errorMsg = res.statusText;
        }
        throw new Error(`❌ Error al exportar (${res.status}): ${errorMsg}`);
      }

      const blob = await res.blob();
      console.log("✅ Blob recibido, tamaño:", blob.size, "bytes");

      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `generated_project_${diagramId}.zip`;
      document.body.appendChild(link);
      link.click();
      link.remove();

      window.URL.revokeObjectURL(url);
      console.log("📦 Descarga completada para:", diagramId);
    } catch (err) {
      console.error("⚠️ Error en exportDiagram:", err);
      alert(err.message);
    } finally {
      setLoading(false);
    }
  }

  return { exportDiagram, loading };
}
