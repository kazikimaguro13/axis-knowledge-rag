"use client";

import { useEffect, useState } from "react";

interface Props {
  text: string;
  citedIds: string[];
  isLoading: boolean;
  isDummy: boolean;
  model: string | null;
  error: string | null;
}

const CITATION_RE = /\[(doc_\d+)\]/g;

function renderWithCitations(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  CITATION_RE.lastIndex = 0;
  while ((m = CITATION_RE.exec(text)) !== null) {
    if (m.index > lastIndex) {
      parts.push(text.slice(lastIndex, m.index));
    }
    parts.push(
      <a
        key={`cite-${i++}`}
        href={`#${m[1]}`}
        className="mx-0.5 rounded bg-emerald-100 px-1 text-xs font-medium text-emerald-700 no-underline hover:bg-emerald-200"
      >
        [{m[1]}]
      </a>
    );
    lastIndex = m.index + m[0].length;
  }
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }
  return parts;
}

export default function AnswerPanel({
  text,
  citedIds,
  isLoading,
  isDummy,
  model,
  error,
}: Props) {
  const [displayed, setDisplayed] = useState("");
  useEffect(() => {
    if (!text) {
      setDisplayed("");
      return;
    }
    setDisplayed("");
    let i = 0;
    const step = Math.max(1, Math.floor(text.length / 80));
    const id = setInterval(() => {
      i += step;
      if (i >= text.length) {
        setDisplayed(text);
        clearInterval(id);
      } else {
        setDisplayed(text.slice(0, i));
      }
    }, 25);
    return () => clearInterval(id);
  }, [text]);

  if (isLoading) {
    return (
      <section className="space-y-2" aria-live="polite" aria-busy>
        <h2 className="text-lg font-semibold">💡 回答</h2>
        <div className="space-y-2">
          <div className="h-4 w-1/3 animate-pulse rounded bg-slate-200" />
          <div className="h-4 w-full animate-pulse rounded bg-slate-200" />
          <div className="h-4 w-2/3 animate-pulse rounded bg-slate-200" />
        </div>
      </section>
    );
  }

  if (error) {
    return (
      <section role="alert" className="rounded bg-red-50 p-3 text-sm text-red-700">
        ⚠ 回答生成エラー: {error}
      </section>
    );
  }

  if (!text) {
    return null;
  }

  return (
    <section
      aria-live="polite"
      className="space-y-2 rounded border border-emerald-200 bg-emerald-50 p-4"
    >
      <div className="flex items-baseline justify-between">
        <h2 className="text-lg font-semibold">💡 回答</h2>
        <span className="text-xs text-slate-500">
          {isDummy ? "DUMMY mode" : `model: ${model ?? "?"}`}
          {citedIds.length > 0 && `  ·  cited: ${citedIds.join(", ")}`}
        </span>
      </div>
      <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-800">
        {renderWithCitations(displayed)}
      </p>
    </section>
  );
}
