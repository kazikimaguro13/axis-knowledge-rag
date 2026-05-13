// API client for the FastAPI backend. Types mirror backend/src/schemas.py.

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export interface AxisDef {
  name: string;
  type: string;
  values?: string[];
  required?: boolean;
}

export interface AxesResponse {
  axes: AxisDef[];
}

export interface SearchResultPayload {
  id: string;
  title: string;
  score: number;
  axes: Record<string, string | number>;
  body_snippet: string;
  path: string;
  refs: string[];
}

export interface SearchResponse {
  results: SearchResultPayload[];
}

export interface AnswerResponse {
  text: string;
  cited_ids: string[];
  sources: SearchResultPayload[];
  is_dummy: boolean;
  model: string | null;
}

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    throw new Error(`API ${path} failed: ${res.status} ${await res.text()}`);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () =>
    jsonFetch<{ status: string; embedder_mode: string; rag_mode: string }>(
      "/api/health",
    ),
  axes: () => jsonFetch<AxesResponse>("/api/axes"),
  search: (body: {
    query?: string | null;
    filters?: Record<string, string | number>;
    top_k?: number;
  }) =>
    jsonFetch<SearchResponse>("/api/search", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  answer: (body: {
    question: string;
    filters?: Record<string, string | number>;
    top_k?: number;
    max_tokens?: number;
  }) =>
    jsonFetch<AnswerResponse>("/api/answer", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
