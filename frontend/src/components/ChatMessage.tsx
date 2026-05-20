"use client";

import { useRef, useState } from "react";
import type { SearchResultPayload } from "@/lib/api";
import { parseCitations } from "@/lib/citations";
import { postFeedback } from "@/lib/feedbackClient";

export interface ChatMessageData {
  role: "user" | "assistant";
  content: string;
  sources?: SearchResultPayload[];
  rewrittenQuestion?: string | null;
  /** Original user question that produced this assistant turn. */
  userQuestion?: string | null;
}

interface Props {
  msg: ChatMessageData;
  sessionId?: string | null;
}

export function ChatMessage({ msg, sessionId = null }: Props) {
  const [showSources, setShowSources] = useState(false);
  const [highlightedN, setHighlightedN] = useState<number | null>(null);
  const highlightTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // spec_047: 👍 / 👎 on the whole assistant answer (separate from per-source).
  const [answerFeedback, setAnswerFeedback] = useState<"up" | "down" | null>(null);
  // spec_047: per-source feedback state keyed by source id.
  const [sourceFeedback, setSourceFeedback] = useState<
    Record<string, "up" | "down" | null>
  >({});
  const isUser = msg.role === "user";
  const sources = msg.sources ?? [];
  const query = msg.userQuestion ?? null;

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

  // Whole-answer rating: doc_id = null so the backend stores it against the
  // assistant turn rather than a specific source card.
  async function sendAnswerFeedback(rating: 1 | -1) {
    const prev = answerFeedback;
    setAnswerFeedback(rating > 0 ? "up" : "down");
    try {
      await postFeedback({
        query,
        doc_id: null,
        rating,
        session_id: sessionId,
      });
    } catch {
      setAnswerFeedback(prev);
    }
  }

  async function sendSourceFeedback(docId: string, rating: 1 | -1) {
    const prev = sourceFeedback[docId] ?? null;
    setSourceFeedback((s) => ({ ...s, [docId]: rating > 0 ? "up" : "down" }));
    try {
      await postFeedback({
        query,
        doc_id: docId,
        rating,
        session_id: sessionId,
      });
    } catch {
      setSourceFeedback((s) => ({ ...s, [docId]: prev }));
    }
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
        {!isUser && (
          <div className="mt-2 flex gap-2 text-xs">
            <button
              type="button"
              aria-label="この回答は役立った"
              aria-pressed={answerFeedback === "up"}
              disabled={answerFeedback !== null}
              onClick={() => sendAnswerFeedback(1)}
              className={
                "rounded border px-2 py-0.5 transition-colors " +
                (answerFeedback === "up"
                  ? "border-green-400 bg-green-100 text-green-700"
                  : "border-slate-200 text-slate-500 hover:bg-slate-50") +
                (answerFeedback !== null ? " disabled:cursor-default disabled:opacity-80" : "")
              }
            >
              👍
            </button>
            <button
              type="button"
              aria-label="この回答は役に立たなかった"
              aria-pressed={answerFeedback === "down"}
              disabled={answerFeedback !== null}
              onClick={() => sendAnswerFeedback(-1)}
              className={
                "rounded border px-2 py-0.5 transition-colors " +
                (answerFeedback === "down"
                  ? "border-red-400 bg-red-100 text-red-700"
                  : "border-slate-200 text-slate-500 hover:bg-slate-50") +
                (answerFeedback !== null ? " disabled:cursor-default disabled:opacity-80" : "")
              }
            >
              👎
            </button>
          </div>
        )}
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
                  const fb = sourceFeedback[s.id] ?? null;
                  return (
                    <li
                      key={s.id}
                      id={`chat-srcs-${n}`}
                      data-highlighted={isHi ? "true" : "false"}
                      className={
                        "flex flex-wrap items-center gap-2 rounded px-1 text-slate-600 transition-colors duration-500 " +
                        (isHi ? "bg-yellow-100" : "")
                      }
                    >
                      <span>
                        <span className="font-mono text-slate-400">[{n}]</span>{" "}
                        {s.title}{" "}
                        <span className="font-mono text-slate-400">({s.id})</span>{" "}
                        <span className="text-slate-400">
                          score {s.score.toFixed(3)}
                        </span>
                      </span>
                      <span className="ml-auto flex gap-1">
                        <button
                          type="button"
                          aria-label={`[${n}] は役立った`}
                          aria-pressed={fb === "up"}
                          disabled={fb !== null}
                          onClick={() => sendSourceFeedback(s.id, 1)}
                          className={
                            "rounded border px-1 text-[10px] " +
                            (fb === "up"
                              ? "border-green-400 bg-green-100 text-green-700"
                              : "border-slate-200 text-slate-400 hover:bg-slate-50") +
                            (fb !== null ? " disabled:cursor-default disabled:opacity-80" : "")
                          }
                        >
                          👍
                        </button>
                        <button
                          type="button"
                          aria-label={`[${n}] は役に立たなかった`}
                          aria-pressed={fb === "down"}
                          disabled={fb !== null}
                          onClick={() => sendSourceFeedback(s.id, -1)}
                          className={
                            "rounded border px-1 text-[10px] " +
                            (fb === "down"
                              ? "border-red-400 bg-red-100 text-red-700"
                              : "border-slate-200 text-slate-400 hover:bg-slate-50") +
                            (fb !== null ? " disabled:cursor-default disabled:opacity-80" : "")
                          }
                        >
                          👎
                        </button>
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
