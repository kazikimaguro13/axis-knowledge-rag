/**
 * Parse `[N]` (1-indexed) inline citation markers, mirroring
 * backend/src/_citations.py. Used by AnswerPanel / ChatMessage to turn
 * raw answer text into a clickable segment stream.
 *
 * `[1, 2]` is expanded into two separate citation segments so the UI can
 * render two distinct chips with their own click handlers.
 *
 * Markers inside Markdown code fences (```...```) or inline code spans
 * (`...`) are preserved as literal text (spec_039) — `x = arr[1]` inside
 * a code block is not a citation. Logic mirrors `_build_skip_ranges()` /
 * `_is_in_skip_range()` in the Python module.
 */

export type Segment =
  | { kind: "text"; text: string }
  | { kind: "citation"; n: number };

// 1–3 digits per number, with optional whitespace inside CSV form.
const RE_MARKER = /\[(\d{1,3}(?:\s*,\s*\d{1,3})*)\]/g;

// Fenced (```...```) and inline (`...`) code regions to skip.
// JS regex has no DOTALL flag — use [\s\S] to span newlines.
const RE_CODE_SPANS = /(```[^\n]*\n[\s\S]*?\n```)|(`[^`\n]+`)/g;

function buildSkipRanges(text: string): [number, number][] {
  const ranges: [number, number][] = [];
  RE_CODE_SPANS.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = RE_CODE_SPANS.exec(text)) !== null) {
    ranges.push([m.index, m.index + m[0].length]);
  }
  return ranges;
}

function isInSkipRange(pos: number, ranges: [number, number][]): boolean {
  for (const [s, e] of ranges) {
    if (s <= pos && pos < e) return true;
  }
  return false;
}

export function parseCitations(text: string): Segment[] {
  const segments: Segment[] = [];
  const skipRanges = buildSkipRanges(text);
  let lastIndex = 0;
  let m: RegExpExecArray | null;
  RE_MARKER.lastIndex = 0;
  while ((m = RE_MARKER.exec(text)) !== null) {
    if (isInSkipRange(m.index, skipRanges)) {
      continue;
    }
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
