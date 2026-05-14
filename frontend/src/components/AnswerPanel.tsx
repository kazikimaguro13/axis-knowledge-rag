"use client";

import { useEffect, useState } from "react";
import { parseCitations } from "@/lib/citations";
import type { SearchResultPayload } from "@/lib/api";

interface Props {
  text: string;
  citedIds: string[];
  sources?: SearchResultPayload[];
  isLoading: boolean;
  isDummy: boolean;
  model: string | null;
  error: string | null;
  onCitationFocus?: (n: number, sourceId: string | null) => void;
}

function renderWithCitations(
  text: string,
  sources: SearchResultPayload[] | undefined,
  onClick: (n: number) => void,
): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  let i = 0;
  for (const seg of parseCitations(text)) {
    if (seg.kind === "text") {
      parts.push(<span key={`t-${i++}`}>{seg.text}</span>);
    } else {
      const src = sources?.[seg.n - 1];
      parts.push(
        <button
          key={`c-${i++}`}
          type="button"
          onClick={() => onClick(seg.n)}
          title={src ? `${src.title} (${src.id})` : `出典 ${seg.n}`}
          className="citation-marker mx-0.5 inline-flex items-baseline rounded bg-emerald-100 px-1 align-baseline text-xs font-semibold text-emerald-700 hover:bg-yellow-200 focus:outline-none focus:ring-2 focus:ring-yellow-400"
        >
          [{seg.n}]
        </button>,
      );
    }
  }
  return parts;
}

export default function AnswerPanel({
  text,
  citedIds,
  sources,
  isLoading,
  isDummy,
  model,
  error,
  onCitationFocus,
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

  function focusSource(n: number) {
    const src = sources?.[n - 1];
    if (src) {
      const el = document.getElementById(src.id);
      el?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
    onCitationFocus?.(n, src?.id ?? null);
  }

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
        {renderWithCitations(displayed, sources, focusSource)}
      </p>
    </section>
  );
}
