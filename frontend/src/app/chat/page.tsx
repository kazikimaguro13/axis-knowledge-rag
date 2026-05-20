"use client";

import { useEffect, useRef, useState } from "react";
import { ChatInput } from "@/components/ChatInput";
import { ChatMessage, type ChatMessageData } from "@/components/ChatMessage";
import {
  clearStoredSessionId,
  deleteChat,
  getStoredSessionId,
  postChat,
  setStoredSessionId,
} from "@/lib/chatClient";

export default function ChatPage() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessageData[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setSessionId(getStoredSessionId());
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, loading]);

  async function send(question: string) {
    setError(null);
    setMessages((m) => [...m, { role: "user", content: question }]);
    setLoading(true);
    try {
      const res = await postChat({ question, session_id: sessionId });
      setSessionId(res.session_id);
      setStoredSessionId(res.session_id);
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: res.answer,
          sources: res.sources,
          rewrittenQuestion: res.rewritten_question,
          userQuestion: question,
        },
      ]);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  async function reset() {
    if (sessionId) {
      try {
        await deleteChat(sessionId);
      } catch {
        /* ignore — server may have already evicted */
      }
    }
    clearStoredSessionId();
    setSessionId(null);
    setMessages([]);
    setError(null);
  }

  return (
    <section className="space-y-4">
      <div className="flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-bold">💬 Chat</h1>
          <p className="text-sm text-slate-500">
            履歴を保持した対話モード。follow-up は自動で standalone 質問に書き換えられます。
          </p>
        </div>
        <button
          type="button"
          onClick={reset}
          className="rounded border border-slate-300 px-3 py-1 text-sm text-slate-600 hover:bg-slate-100"
        >
          🗑 リセット
        </button>
      </div>

      {sessionId && (
        <p className="text-xs text-slate-400">
          session: <code>{sessionId}</code>
        </p>
      )}

      <div className="min-h-[300px] space-y-3 rounded border border-slate-200 bg-slate-50 p-4">
        {messages.length === 0 && (
          <p className="text-sm text-slate-400">
            下の入力欄から質問してください。例:「RAG とは?」→「それの利点は?」
          </p>
        )}
        {messages.map((m, i) => (
          <ChatMessage key={i} msg={m} sessionId={sessionId} />
        ))}
        {loading && (
          <p className="text-sm text-slate-400" aria-live="polite">
            考え中...
          </p>
        )}
        {error && (
          <p role="alert" className="rounded bg-red-50 p-2 text-sm text-red-700">
            ⚠ {error}
          </p>
        )}
        <div ref={scrollRef} />
      </div>

      <ChatInput onSend={send} disabled={loading} />
    </section>
  );
}
