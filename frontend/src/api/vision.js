import api from "./client";

/**
 * Sube una foto de un diagrama de clases dibujado a mano y devuelve lo que
 * Gemini leyó (clases, atributos, relaciones) SIN crear nada todavía: el
 * resultado es para mostrar como vista previa editable antes de confirmar.
 *
 * Timeout propio, más largo que el default de 10s del cliente: el backend
 * reintenta contra Gemini con backoff (hasta 4 intentos + fallback a otro
 * modelo si el principal está saturado), lo que en el peor caso tarda mucho
 * más que 10s aunque termine respondiendo 200 OK -- sin este override, Axios
 * cortaba la conexión antes de que llegara la respuesta exitosa y el
 * frontend mostraba "no se pudo leer la imagen" pese a que el backend sí
 * la había leído bien.
 */
export const detectDiagramFromImage = async (file) => {
  const form = new FormData();
  form.append("file", file);
  const res = await api.post("/vision/detect", form, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 90000,
  });
  return res.data; // { classes, relations, warning }
};

/**
 * Crea un diagrama nuevo con la estructura ya revisada por el usuario.
 * Devuelve { diagram_id, classes_created, attributes_created,
 * relations_created, warnings }.
 */
export const applyDetectedDiagram = async ({ title, classes, relations }) => {
  const res = await api.post("/vision/apply", { title, classes, relations });
  return res.data;
};
