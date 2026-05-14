"use client";

import { SearchResultPayload } from "@/lib/api";

interface Props {
  result: SearchResultPayload;
  cited?: boolean;
  /** Index in the source list (1-based) to render as a `[N]` chip header. */
  n?: number;
  /** Transient flash applied when the user clicks the matching `[N]` marker. */
  highlighted?: boolean;
}

export default function ResultCard({ result, cited = false, n, highlighted = false }: Props) {
  return (
    <article
      id={result.id}
      data-highlighted={highlighted ? "true" : "false"}
      className={
        "scroll-mt-4 rounded border p-4 shadow-sm transition-colors duration-500 " +
        (highlighted
          ? "border-yellow-400 bg-yellow-100"
          : cited
          ? "border-emerald-400 bg-white"
          : "border-slate-200 bg-white")
      }
    >
      <div className="mb-2 flex items-baseline justify-between gap-3">
        <h3 className="text-base font-semibold">
          {n != null && (
            <span className="mr-2 rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">
              [{n}]
            </span>
          )}
          {result.title}
          {cited && (
            <span className="ml-2 rounded bg-emerald-100 px-2 py-0.5 text-xs text-emerald-700">
              ★ cited
            </span>
          )}
        </h3>
        <span className="text-xs text-slate-500">score {result.score.toFixed(3)}</span>
      </div>
      <p className="mb-2 text-xs text-slate-500">
        {Object.entries(result.axes)
          .map(([k, v]) => `${k}: ${v}`)
          .join("  ·  ")}
      </p>
      <p className="text-sm text-slate-800">{result.body_snippet}</p>
      <p className="mt-2 truncate text-xs text-slate-400" title={result.path}>
        {result.id}  ·  {result.path}
      </p>
    </article>
  );
}
