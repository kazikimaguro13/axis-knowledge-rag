"use client";

import { SearchResultPayload } from "@/lib/api";

interface Props {
  result: SearchResultPayload;
  cited?: boolean;
}

export default function ResultCard({ result, cited = false }: Props) {
  return (
    <article
      id={result.id}
      className={
        "scroll-mt-4 rounded border bg-white p-4 shadow-sm transition " +
        (cited ? "border-emerald-400" : "border-slate-200")
      }
    >
      <div className="mb-2 flex items-baseline justify-between gap-3">
        <h3 className="text-base font-semibold">
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
