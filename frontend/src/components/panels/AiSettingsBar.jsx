// src/components/panels/AiSettingsBar.jsx
//
// Franja del chat con la configuración de la IA del diagrama (Fase 2).
//
//  - CU-18 Entrega de soluciones: "la IA va a tener la capacidad de entregar
//    soluciones cuando así se lo requieran. Eso va a ser configurable".
//  - CU-17 Proveedor de IA: Gemini (nube) o un modelo local / en Colab con
//    API compatible con OpenAI (Ollama, LM Studio, vLLM...).
//
// Todo el equipo ve el estado; solo el dueño del diagrama puede cambiarlo.
// Cada cambio llega a todas las sesiones por WebSocket (`ai.settings`).

import { useEffect, useState } from "react";
import { getAiSettings, testAiSettings, updateAiSettings } from "../../api/chat";
import { onEvent } from "../../api/realtime";
import Icon from "../common/Icon";

const PRESETS = [
  { label: "Ollama (esta PC)", base_url: "http://localhost:11434/v1", model: "llama3.2" },
  { label: "LM Studio", base_url: "http://localhost:1234/v1", model: "" },
  { label: "Colab / vLLM", base_url: "https://<tu-tunel>.trycloudflare.com/v1", model: "" },
];

function Switch({ on, onClick, disabled, label }) {
  return (
    <button
      role="switch"
      aria-checked={on}
      aria-label={label}
      title={label}
      onClick={onClick}
      disabled={disabled}
      style={{
        flex: "none", width: 32, height: 18, borderRadius: 999, border: "none", padding: 2,
        cursor: disabled ? "wait" : "pointer",
        background: on ? "var(--accent)" : "var(--border-strong)",
        display: "flex", justifyContent: on ? "flex-end" : "flex-start", transition: "background .15s",
      }}
    >
      <span style={{ width: 14, height: 14, borderRadius: 999, background: "#fff", display: "block" }} />
    </button>
  );
}

function ProviderForm({ diagramId, settings, onSaved, onClose }) {
  const [provider, setProvider] = useState(settings.provider_is_default ? "default" : settings.provider);
  const [baseUrl, setBaseUrl] = useState(settings.provider === "openai_compatible" ? settings.base_url || "" : "");
  const [model, setModel] = useState(settings.provider === "openai_compatible" ? settings.model || "" : "");
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  const save = async () => {
    setBusy(true);
    setResult(null);
    try {
      const body = { provider };
      if (provider === "openai_compatible") Object.assign(body, { base_url: baseUrl.trim(), model: model.trim() });
      if (provider !== "default" && apiKey) body.api_key = apiKey;
      const s = await updateAiSettings(diagramId, body);
      onSaved(s);
      setApiKey("");
      const t = await testAiSettings(diagramId);
      setResult(t);
    } catch (err) {
      const d = err?.response?.data?.detail;
      setResult({ ok: false, detail: Array.isArray(d) ? d.map((x) => x.msg).join(" · ") : d || "No se pudo guardar." });
    } finally {
      setBusy(false);
    }
  };

  const row = { display: "grid", gap: 4 };
  return (
    <div style={{ padding: "var(--sp-3) var(--sp-4)", borderBottom: "1px solid var(--border)", display: "grid", gap: "var(--sp-2)", fontSize: 12 }}>
      <div style={{ display: "flex", alignItems: "center" }}>
        <strong style={{ flex: 1 }}>Proveedor de IA de este diagrama</strong>
        <button className="btn btn-ghost btn-icon btn-sm" onClick={onClose} title="Cerrar configuración">
          <Icon name="close" size={13} />
        </button>
      </div>
      <label style={row}>
        <span className="text-muted">Modelo que responde en el chat</span>
        <select className="input input-sm" value={provider} onChange={(e) => setProvider(e.target.value)}>
          <option value="default">Por defecto del servidor</option>
          <option value="gemini">Gemini (Google AI Studio, nube)</option>
          <option value="openai_compatible">Modelo local / Colab (API compatible con OpenAI)</option>
        </select>
      </label>
      {provider === "openai_compatible" && (
        <>
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
            {PRESETS.map((p) => (
              <button key={p.label} className="btn btn-sm" type="button"
                onClick={() => { setBaseUrl(p.base_url); if (p.model) setModel(p.model); }}>
                {p.label}
              </button>
            ))}
          </div>
          <label style={row}>
            <span className="text-muted">Endpoint (termina en /v1)</span>
            <input className="input input-sm" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="http://localhost:11434/v1" />
          </label>
          <label style={row}>
            <span className="text-muted">Modelo</span>
            <input className="input input-sm" value={model} onChange={(e) => setModel(e.target.value)}
              placeholder="llama3.2, qwen2.5:7b, ..." />
          </label>
        </>
      )}
      {provider !== "default" && (
        <label style={row}>
          <span className="text-muted">
            Token / API key {settings.has_api_key ? "(hay uno guardado; dejalo vacío para conservarlo)" : "(opcional)"}
          </span>
          <input className="input input-sm" type="password" autoComplete="off" value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={provider === "gemini" ? "Vacío = la clave del servidor" : "Vacío si el servidor no pide token"} />
        </label>
      )}
      <div style={{ display: "flex", gap: "var(--sp-2)", alignItems: "center" }}>
        <button className="btn btn-primary btn-sm" onClick={save} disabled={busy}>
          {busy ? <Icon name="loader" size={13} className="spinning" /> : <Icon name="check" size={13} />}
          Guardar y probar conexión
        </button>
      </div>
      {result && (
        <div style={{ color: result.ok ? "var(--success)" : "var(--danger)", display: "flex", gap: 6 }}>
          <Icon name={result.ok ? "check" : "warning"} size={13} />
          <span>{result.ok ? `Conectado a ${result.provider_label}. ${result.detail}` : result.detail}</span>
        </div>
      )}
    </div>
  );
}

export default function AiSettingsBar({ diagramId, isOwner, initialEnabled = false }) {
  const [settings, setSettings] = useState({ solutions_enabled: initialEnabled, provider_label: "", provider_is_default: true });
  const [saving, setSaving] = useState(false);
  const [changedBy, setChangedBy] = useState(null);
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    let alive = true;
    getAiSettings(diagramId).then((s) => alive && setSettings(s)).catch(() => {});
    const off = onEvent("ai.settings", (s) => {
      if (!s) return;
      setSettings((prev) => ({ ...prev, ...s }));
      setChangedBy(s.changed_by || null);
    });
    return () => {
      alive = false;
      off();
    };
  }, [diagramId]);

  const enabled = !!settings.solutions_enabled;

  const toggle = async () => {
    if (!isOwner || saving) return;
    setSaving(true);
    try {
      setSettings(await updateAiSettings(diagramId, { solutions_enabled: !enabled }));
      setChangedBy(null);
    } catch {
      /* el switch vuelve a mostrar el valor real */
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <div
        style={{
          display: "grid", gap: 4, padding: "6px var(--sp-4)", borderBottom: "1px solid var(--border)",
          background: enabled ? "var(--accent-soft)" : "var(--surface-2)", fontSize: 11,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-2)" }}>
          <Icon name="sparkles" size={12} style={{ color: enabled ? "var(--accent)" : "var(--text-muted)", flex: "none" }} />
          <span style={{ flex: 1, minWidth: 0, color: "var(--text)" }}>
            {enabled ? "La IA puede entregar soluciones de diseño completas" : "La IA solo hace ediciones puntuales y mentoría"}
            {changedBy && <span className="text-muted"> · cambiado por {changedBy}</span>}
          </span>
          {isOwner ? (
            <Switch on={enabled} onClick={toggle} disabled={saving} label="La IA puede entregar soluciones" />
          ) : (
            <span className="text-muted" title="Solo el dueño del diagrama puede cambiarlo" style={{ flex: "none" }}>
              <Icon name="lock" size={11} />
            </span>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-2)", color: "var(--text-muted)" }}>
          <Icon name="cursor" size={11} style={{ flex: "none" }} />
          <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
            title={settings.provider_label}>
            Modelo: {settings.provider_label || "…"}
            {settings.provider === "openai_compatible" && " · local/Colab"}
          </span>
          {isOwner && (
            <button className="btn btn-ghost btn-sm" style={{ height: 20, padding: "0 6px", fontSize: 11 }}
              onClick={() => setEditing((v) => !v)}>
              {editing ? "Ocultar" : "Cambiar"}
            </button>
          )}
        </div>
      </div>
      {isOwner && editing && (
        <ProviderForm diagramId={diagramId} settings={settings} onSaved={setSettings} onClose={() => setEditing(false)} />
      )}
    </>
  );
}
