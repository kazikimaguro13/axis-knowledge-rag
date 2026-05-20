"use client";

import { useState } from "react";
import { SearchResultPayload } from "@/lib/api";
import { postFeedback } from "@/lib/feedbackClient";

interface Props {
  result: SearchResultPayload;
  cited?: boolean;
  /** Index in the source list (1-based) to render as a `[N]` chip header. */
  n?: number;
  /** Transient flash applied when the user clicks the matching `[N]` marker. */
  highlighted?: boolean;
  /** Originating query string — captured alongside the 👍/👎 signal. */
  query?: string | null;
  /** Chat session id, when this card is rendered under a chat turn. */
  sessionId?: string | null;
}

export default function ResultCard({
  result,
  cited = false,
  n,
  highlighted = false,
  query = null,
  sessionId = null,
}: Props) {
  const [feedback, setFeedback] = useState<"up" | "down" | null>(null);

  // spec_047: optimistic UI — the visual state flips on click; only revert
  // if the API rejects the write. The button is disabled once tapped so a
  // single result card produces at most one signal per session.
  const send = async (rating: 1 | -1) => {
    const prev = feedback;
    setFeedback(rating > 0 ? "up" : "down");
    try {
      await postFeedback({
        query,
        doc_id: result.id,
        rating,
        session_id: sessionId,
      });
    } catch {
      setFeedback(prev);
    }
  };

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
      <div className="mt-2 flex gap-2 text-sm">
        <button
          type="button"
          aria-label="役立った"
          aria-pressed={feedback === "up"}
          disabled={feedback !== null}
          onClick={() => send(1)}
          className={
            "rounded border px-2 py-0.5 text-xs transition-colors " +
            (feedback === "up"
              ? "border-green-400 bg-green-100 text-green-700"
              : "border-slate-200 text-slate-500 hover:bg-slate-50") +
            (feedback !== null ? " disabled:cursor-default disabled:opacity-80" : "")
          }
        >
          👍 役立った
        </button>
        <button
          type="button"
          aria-label="役に立たなかった"
          aria-pressed={feedback === "down"}
          disabled={feedback !== null}
          onClick={() => send(-1)}
          className={
            "rounded border px-2 py-0.5 text-xs transition-colors " +
            (feedback === "down"
              ? "border-red-400 bg-red-100 text-red-700"
              : "border-slate-200 text-slate-500 hover:bg-slate-50") +
            (feedback !== null ? " disabled:cursor-default disabled:opacity-80" : "")
          }
        >
          👎 ふつう
        </button>
      </div>
    </article>
  );
}
