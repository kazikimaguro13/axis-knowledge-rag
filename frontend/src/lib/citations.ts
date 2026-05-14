/**
 * Parse `[N]` (1-indexed) inline citation markers, mirroring
 * backend/src/_citations.py. Used by AnswerPanel / ChatMessage to turn
 * raw answer text into a clickable segment stream.
 *
 * `[1, 2]` is expanded into two separate citation segments so the UI can
 * render two distinct chips with their own click handlers.
 */

export type Segment =
  | { kind: "text"; text: string }
  | { kind: "citation"; n: number };

// 1–3 digits per number, with optional whitespace inside CSV form.
const RE_MARKER = /\[(\d{1,3}(?:\s*,\s*\d{1,3})*)\]/g;

export function parseCitations(text: string): Segment[] {
  const segments: Segment[] = [];
  let lastIndex = 0;
  let m: RegExpExecArray | null;
  RE_MARKER.lastIndex = 0;
  while ((m = RE_MARKER.exec(text)) !== null) {
    if (m.index > lastIndex) {
      segments.push({ kind: "text", text: text.slice(lastIndex, m.index) });
    }
    for (const piece of m[1].split(",")) {
      const n = parseInt(piece.trim(), 10);
      if (!Number.isNaN(n)) segments.push({ kind: "citation", n });
    }
    lastIndex = m.index + m[0].length;
  }
  if (lastIndex < text.length) {
    segments.push({ kind: "text", text: text.slice(lastIndex) });
  }
  return segments;
}
