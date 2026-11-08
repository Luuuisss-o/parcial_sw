// src/components/common/ChatMarkdown.jsx
//
// Renderizador mínimo de markdown para las respuestas de la IA en el chat.
// Gemini responde con **negritas**, `código`, listas y a veces títulos; sin
// esto el chat mostraba los asteriscos crudos.
//
// Construye elementos de React (nunca usa dangerouslySetInnerHTML), así que
// el texto del modelo no puede inyectar HTML. Soporta solo lo que tiene
// sentido en un panel angosto:
//   - párrafos y saltos de línea
//   - listas con "-", "*", "•" o "1." / "1)" (con sangría por nivel)
//   - títulos "#…" → línea en negrita
//   - separadores "---" → se omiten
//   - **negrita**, *cursiva* / _cursiva_, `código`, y menciones @IA

const INLINE_RE =
  /(\\[*_`#\\]|\*\*[^*\n]+?\*\*|__[^_\n]+?__|`[^`\n]+?`|(?<![\w*])\*(?!\s)[^*\n]+?(?<!\s)\*(?!\w)|(?<![\w])_(?!\s)[^_\n]+?(?<!\s)_(?![\w])|(?<![\w@.])@(?:ia|ai|asistente)\b)/gi;

const MENTION_RE = /(?<![\w@.])@(?:ia|ai|asistente)\b/gi;

const codeStyle = {
  fontFamily: "var(--font-mono)",
  fontSize: "0.92em",
  padding: "0 4px",
  borderRadius: 4,
  background: "var(--surface-3)",
};

function renderInline(text, keyPrefix) {
  const out = [];
  let last = 0;
  let i = 0;
  for (const m of text.matchAll(INLINE_RE)) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const tok = m[0];
    const key = `${keyPrefix}-${i++}`;
    if (tok.startsWith("\\")) out.push(tok.slice(1)); // \* → * literal
    else if (tok.startsWith("**") || tok.startsWith("__")) out.push(<strong key={key}>{tok.slice(2, -2)}</strong>);
    else if (tok.startsWith("`")) out.push(<code key={key} style={codeStyle}>{tok.slice(1, -1)}</code>);
    else if (tok.startsWith("@"))
      out.push(
        <span key={key} style={{ fontWeight: 700, textDecoration: "underline", textUnderlineOffset: 2 }}>
          {tok}
        </span>
      );
    else out.push(<em key={key}>{tok.slice(1, -1)}</em>);
    last = m.index + tok.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

const LIST_RE = /^(\s*)(?:[-*•]|(\d+)[.)])\s+(.*)$/;
const HEADING_RE = /^\s*#{1,6}\s+(.*)$/;
const HR_RE = /^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/;

/** Texto con formato. `markdown=false` solo resalta las menciones @IA. */
export default function ChatMarkdown({ text, markdown = true }) {
  if (!markdown) {
    // Mensajes de personas: texto tal cual, solo se resaltan las menciones.
    const parts = [];
    let last = 0;
    for (const m of text.matchAll(MENTION_RE)) {
      if (m.index > last) parts.push(text.slice(last, m.index));
      parts.push(
        <span key={m.index} style={{ fontWeight: 700, textDecoration: "underline", textUnderlineOffset: 2 }}>
          {m[0]}
        </span>
      );
      last = m.index + m[0].length;
    }
    if (last < text.length) parts.push(text.slice(last));
    return <span style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{parts}</span>;
  }

  const blocks = [];
  let para = [];
  const flush = () => {
    if (para.length) {
      blocks.push({ type: "p", lines: para });
      para = [];
    }
  };

  for (const raw of text.replace(/\r\n/g, "\n").split("\n")) {
    if (!raw.trim()) {
      flush();
      continue;
    }
    if (HR_RE.test(raw)) {
      flush();
      continue;
    }
    const h = raw.match(HEADING_RE);
    if (h) {
      flush();
      blocks.push({ type: "h", text: h[1] });
      continue;
    }
    const li = raw.match(LIST_RE);
    if (li) {
      flush();
      const level = Math.min(Math.floor(li[1].replace(/\t/g, "  ").length / 2), 3);
      blocks.push({ type: "li", level, num: li[2], text: li[3] });
      continue;
    }
    para.push(raw.trim());
  }
  flush();

  return (
    <div style={{ display: "grid", gap: 4, wordBreak: "break-word" }}>
      {blocks.map((b, i) => {
        if (b.type === "h")
          return (
            <div key={i} style={{ fontWeight: 700, marginTop: i ? 4 : 0 }}>
              {renderInline(b.text, `h${i}`)}
            </div>
          );
        if (b.type === "li")
          return (
            <div key={i} style={{ display: "flex", gap: 6, paddingLeft: b.level * 14 }}>
              <span style={{ flex: "none", minWidth: b.num ? 16 : 8, color: "var(--text-muted)" }}>
                {b.num ? `${b.num}.` : "•"}
              </span>
              <span style={{ minWidth: 0 }}>{renderInline(b.text, `l${i}`)}</span>
            </div>
          );
        return (
          <div key={i}>
            {b.lines.map((l, j) => (
              <span key={j}>
                {j > 0 && <br />}
                {renderInline(l, `p${i}-${j}`)}
              </span>
            ))}
          </div>
        );
      })}
    </div>
  );
}
