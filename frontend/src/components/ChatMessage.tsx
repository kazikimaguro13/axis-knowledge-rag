"use client";

import { useState } from "react";
import type { SearchResultPayload } from "@/lib/api";

export interface ChatMessageData {
  role: "user" | "assistant";
  content: string;
  sources?: SearchResultPayload[];
  rewrittenQuestion?: string | null;
}

interface Props {
  msg: ChatMessageData;
}

const CITATION_RE = /\[(doc_\d+)\]/g;

function renderWithCitations(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  CITATION_RE.lastIndex = 0;
  while ((m = CITATION_RE.exec(text)) !== null) {
    if (m.index > lastIndex) parts.push(text.slice(lastIndex, m.index));
    parts.push(
      <span
        key={`cite-${i++}`}
        className="mx-0.5 rounded bg-emerald-100 px-1 text-xs font-medium text-emerald-700"
      >
        [{m[1]}]
      </span>,
    );
    lastIndex = m.index + m[0].length;
  }
  if (lastIndex < text.length) parts.push(text.slice(lastIndex));
  return parts;
}

export function ChatMessage({ msg }: Props) {
  const [showSources, setShowSources] = useState(false);
  const isUser = msg.role === "user";
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
          {isUser ? msg.content : renderWithCitations(msg.content)}
        </p>
        {!isUser && msg.sources && msg.sources.length > 0 && (
          <div className="mt-2 border-t border-slate-100 pt-2 text-xs">
            <button
              type="button"
              onClick={() => setShowSources((s) => !s)}
              className="text-slate-500 hover:underline"
            >
              📚 出典 {msg.sources.length} 件 {showSources ? "▲" : "▼"}
            </button>
            {showSources && (
              <ul className="mt-2 space-y-1">
                {msg.sources.map((s) => (
                  <li key={s.id} className="text-slate-600">
                    <span className="font-mono text-slate-400">[{s.id}]</span>{" "}
                    {s.title}{" "}
                    <span className="text-slate-400">
                      (score {s.score.toFixed(3)})
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
