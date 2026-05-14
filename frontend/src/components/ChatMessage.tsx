"use client";

import { useRef, useState } from "react";
import type { SearchResultPayload } from "@/lib/api";
import { parseCitations } from "@/lib/citations";

export interface ChatMessageData {
  role: "user" | "assistant";
  content: string;
  sources?: SearchResultPayload[];
  rewrittenQuestion?: string | null;
}

interface Props {
  msg: ChatMessageData;
}

export function ChatMessage({ msg }: Props) {
  const [showSources, setShowSources] = useState(false);
  const [highlightedN, setHighlightedN] = useState<number | null>(null);
  const highlightTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isUser = msg.role === "user";
  const sources = msg.sources ?? [];

  function focusCitation(n: number) {
    if (!sources[n - 1]) return;
    setShowSources(true);
    if (highlightTimer.current) clearTimeout(highlightTimer.current);
    setHighlightedN(n);
    highlightTimer.current = setTimeout(() => setHighlightedN(null), 2500);
    // Defer scrollIntoView one tick so the list has expanded.
    setTimeout(() => {
      const list = document.getElementById(`chat-srcs-${n}`);
      list?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }, 30);
  }

  function renderBody(text: string): React.ReactNode[] {
    const parts: React.ReactNode[] = [];
    let i = 0;
    for (const seg of parseCitations(text)) {
      if (seg.kind === "text") {
        parts.push(<span key={`t-${i++}`}>{seg.text}</span>);
      } else {
        const src = sources[seg.n - 1];
        parts.push(
          <button
            key={`c-${i++}`}
            type="button"
            onClick={() => focusCitation(seg.n)}
            disabled={!src}
            title={src ? `${src.title} (${src.id})` : `出典 ${seg.n}`}
            className="citation-marker mx-0.5 inline-flex items-baseline rounded bg-emerald-100 px-1 text-xs font-semibold text-emerald-700 hover:bg-yellow-200 disabled:cursor-default disabled:opacity-60"
          >
            [{seg.n}]
          </button>,
        );
      }
    }
    return parts;
  }

  return (
    <div className={"flex " + (isUser ? "justify-end" : "justify-start")}>
      <div
        className={
          "max-w-[85%] rounded-lg px-4 py-2 text-sm leading-relaxed " +
          (isUser
            ? "bg-blue-600 text-white"
            : "bg-white text-slate-800 border border-slate-200")
        }
      >
        {!isUser && msg.rewrittenQuestion && (
          <p className="mb-1 text-xs italic text-slate-400">
            🔁 rewritten: <code className="text-slate-500">{msg.rewrittenQuestion}</code>
          </p>
        )}
        <p className="whitespace-pre-wrap">
          {isUser ? msg.content : renderBody(msg.content)}
        </p>
        {!isUser && sources.length > 0 && (
          <div className="mt-2 border-t border-slate-100 pt-2 text-xs">
            <button
              type="button"
              onClick={() => setShowSources((s) => !s)}
              className="text-slate-500 hover:underline"
            >
              📚 出典 {sources.length} 件 {showSources ? "▲" : "▼"}
            </button>
            {showSources && (
              <ul className="mt-2 space-y-1">
                {sources.map((s, idx) => {
                  const n = idx + 1;
                  const isHi = highlightedN === n;
                  return (
                    <li
                      key={s.id}
                      id={`chat-srcs-${n}`}
                      data-highlighted={isHi ? "true" : "false"}
                      className={
                        "rounded px-1 text-slate-600 transition-colors duration-500 " +
                        (isHi ? "bg-yellow-100" : "")
                      }
                    >
                      <span className="font-mono text-slate-400">[{n}]</span>{" "}
                      {s.title}{" "}
                      <span className="font-mono text-slate-400">({s.id})</span>{" "}
                      <span className="text-slate-400">
                        score {s.score.toFixed(3)}
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
