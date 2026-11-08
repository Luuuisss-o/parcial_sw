# Reglas de desarrollo — parcial_sw

## CÓDIGO, BASE DE DATOS Y DOCUMENTACIÓN DEBEN MANTENER COHERENCIA

## Checklist obligatorio al modificar cualquier funcionalidad

Antes de dar por terminado un cambio, verificar cada uno de estos puntos que aplique:

### Backend
- [ ] ¿El router nuevo/modificado está registrado en `backend/app/main.py` (`app.include_router(...)`)?
- [ ] ¿El endpoint exige `Depends(get_current_user)` si debería (comparar contra el resto de la API — la única excepción conocida y ya señalada como hallazgo es `export.py`)?
- [ ] ¿El endpoint valida `_accessible_diagram_filter`/`get_my_diagram`/`get_my_class`/etc. si opera sobre un diagrama de un usuario?
- [ ] ¿Los schemas Pydantic (`schemas/`) reflejan exactamente el shape real de request/response, incluidos los alias español/inglés si el modelo ORM usa nombres en español?
- [ ] ¿Se agregaron migraciones Alembic si se tocó un modelo (`models/uml.py`, `models/user.py`)? ¿El `down_revision` encadena correctamente con la última migración existente?
- [ ] ¿Se actualizó `services/ai_tools.py` (definición de tools) si el cambio afecta algo que el asistente de IA puede tocar?

### Frontend
- [ ] ¿El archivo en `src/api/` que consume el enduevo/modificado. refleja el shape real (incluidos los campos español/inglés)?
- [ ] ¿Se probó el flujo en el navegador (no asumir que compila = que funciona)?
- [ ] ¿Los timeouts de Axios están ajustados si el endpoint puede tardar (patrón ya usado en `/vision/detect` y `/voice/transcribe`)?

### Mobile
- [ ] ¿El cambio de contrato de API impacta `mobile/lib/services/api_client.dart` o `realtime_service.dart`? Si sí, actualizarlos también — mobile consume el mismo backend que la web.
- [ ] ¿El asistente offline (`local_llm_service.dart`, `assistant_screen.dart`) necesita reflejar el mismo conjunto de tools que `ai_tools.py` si se agregó/quitó una tool?
- [ ] No asumir que mobile compila solo porque el código Dart está escrito — confirmar con `flutter analyze`/`flutter build` antes de dar por buena una funcionalidad ahí.

### Base de datos
- [ ] Todo cambio de modelo necesita su migración Alembic correspondiente, generada o escrita a mano, con `upgrade()` y `downgrade()` simétricos.
- [ ] Si se agrega una restricción de unicidad nueva, decidir explícitamente si va también a nivel de router (mensaje de error amigable) además de la constraint SQL — el patrón ya usado es tener ambas (ver `atributo`/`metodo`), no solo una.

### API / contratos
- [ ] Antes de cambiar el shape de un endpoint ya consumido, buscarlo en `frontend/src/api/` Y en `mobile/lib/services/` — un cambio de contrato rompe a los dos si no se actualizan ambos.
- [ ] Actualizar `docs/contexto/CONTRATOS_API.md` si se agrega, quita o cambia el shape de un endpoint.

### Casos de uso / diagramas / documentación académica
- [ ] Si la funcionalidad es nueva (como voz), agregarla a `docs/contexto/CONTEXTO_DOCUMENTACION.md` como caso de uso con su matriz de trazabilidad.
- [ ] No inventar clases de análisis genéricas que no existen en el código real.

### Pruebas
- [ ] No se detectó una carpeta de tests automatizados en este audit (no confirmado si existe fuera de lo revisado) — cualquier cambio nuevo debería, como mínimo, probarse manualmente end-to-end (navegador + backend levantado) antes de considerarse terminado, dado que no hay red de seguridad automatizada confirmada.

### Documentación
- [ ] Actualizar `docs/contexto/ESTADO_ACTUAL.md` con la fecha y el resumen del cambio.
- [ ] Si el cambio corrige una inconsistencia ya señalada en estos documentos (ej. el docstring de `ai_assistant.py` sobre dónde se transcribe la voz), quitar la mención de "problema conocido" del documento correspondiente.
- [ ] Nunca copiar ciegamente contenido de `CONTEXTO_PROYECTO.md`/`ARQUITECTURA.md`/`COMO_EMPEZAR_SESION.md` de la raíz sin verificar contra el código — ya se encontraron contradicciones reales (ver `CONTEXTO_MOBILE.md`, sección de estado de compilación).

## Regla general

Si no se puede confirmar algo leyendo el código, se declara explícitamente como "no confirmado" en la documentación. No se asume, no se inventa.
