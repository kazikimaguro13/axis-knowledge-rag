// Chat API client. Wraps /api/chat for the conversational RAG path and
// keeps the active session_id in localStorage so reloading /chat preserves
// the conversation (until the user explicitly resets it).

import type { SearchResultPayload } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const STORAGE_KEY = "axis-chat-session-id";

export interface ChatRequest {
  question: string;
  session_id?: string | null;
  filters?: Record<string, string | number>;
  top_k?: number;
}

export interface ChatResponse {
  session_id: string;
  question: string;
  rewritten_question: string | null;
  answer: string;
  cited_ids: string[];
  sources: SearchResultPayload[];
  is_dummy: boolean;
  model: string | null;
}

export async function postChat(body: ChatRequest): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`/api/chat failed: ${res.status} ${await res.text()}`);
  }
  return (await res.json()) as ChatResponse;
}

export async function deleteChat(sessionId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/chat/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
  });
  if (!res.ok && res.status !== 404) {
    throw new Error(`DELETE /api/chat failed: ${res.status}`);
  }
}

export function getStoredSessionId(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setStoredSessionId(id: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, id);
  } catch {
    /* ignore quota / privacy errors */
  }
}

export function clearStoredSessionId(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
}
