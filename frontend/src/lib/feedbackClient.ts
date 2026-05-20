// spec_047: 👍 / 👎 feedback client.
// Posts to the backend `/api/feedback` endpoint, mirroring
// backend/src/schemas.py:FeedbackRequest.

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export interface FeedbackPayload {
  query?: string | null;
  doc_id?: string | null;
  rating: 1 | -1 | 0;
  session_id?: string | null;
  note?: string | null;
}

export interface FeedbackResponse {
  feedback_id: string;
}

export async function postFeedback(
  payload: FeedbackPayload,
): Promise<FeedbackResponse> {
  const res = await fetch(`${API_BASE}/api/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(
      `feedback POST failed: ${res.status} ${await res.text()}`,
    );
  }
  return (await res.json()) as FeedbackResponse;
}
