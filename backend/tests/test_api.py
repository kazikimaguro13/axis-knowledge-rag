from fastapi.testclient import TestClient

from backend.src.api import app


def test_health() -> None:
    with TestClient(app) as client:
        resp = client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "embedder_mode" in body


def test_search_empty() -> None:
    with TestClient(app) as client:
        resp = client.post(
            "/api/search",
            json={"query": "test", "top_k": 3},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "results" in body


def test_answer_dummy() -> None:
    with TestClient(app) as client:
        resp = client.post(
            "/api/answer",
            json={"question": "test", "top_k": 3},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "text" in body
        assert "cited_ids" in body
        assert "sources" in body


def test_axes() -> None:
    with TestClient(app) as client:
        resp = client.get("/api/axes")
        assert resp.status_code == 200
        body = resp.json()
        assert "axes" in body


# ---------------------------------------------------------------------------
# spec_032: /api/chat
# ---------------------------------------------------------------------------


def test_chat_creates_session() -> None:
    with TestClient(app) as client:
        resp = client.post("/api/chat", json={"question": "RAG とは?"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"]
        assert "answer" in body
        assert isinstance(body["cited_ids"], list)
        assert isinstance(body["sources"], list)
        assert body["question"] == "RAG とは?"


def test_chat_reuses_session() -> None:
    with TestClient(app) as client:
        r1 = client.post("/api/chat", json={"question": "RAG とは?"}).json()
        sid = r1["session_id"]
        r2 = client.post(
            "/api/chat",
            json={"question": "それの利点は?", "session_id": sid},
        )
        assert r2.status_code == 200
        assert r2.json()["session_id"] == sid


def test_chat_history_endpoint() -> None:
    with TestClient(app) as client:
        sid = client.post(
            "/api/chat", json={"question": "RAG とは?"}
        ).json()["session_id"]
        client.post(
            "/api/chat",
            json={"question": "それの利点は?", "session_id": sid},
        )
        resp = client.get(f"/api/chat/{sid}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == sid
        # 2 user + 2 assistant
        assert len(body["messages"]) == 4
        roles = [m["role"] for m in body["messages"]]
        assert roles == ["user", "assistant", "user", "assistant"]


def test_chat_history_unknown_session_returns_404() -> None:
    with TestClient(app) as client:
        resp = client.get("/api/chat/does-not-exist")
        assert resp.status_code == 404


def test_chat_delete_endpoint() -> None:
    with TestClient(app) as client:
        sid = client.post(
            "/api/chat", json={"question": "hello"}
        ).json()["session_id"]
        resp = client.delete(f"/api/chat/{sid}")
        assert resp.status_code == 204
        # Second delete is 404
        resp2 = client.delete(f"/api/chat/{sid}")
        assert resp2.status_code == 404
        # After delete, history endpoint also 404
        resp3 = client.get(f"/api/chat/{sid}")
        assert resp3.status_code == 404


def test_chat_validation_rejects_empty_question() -> None:
    with TestClient(app) as client:
        resp = client.post("/api/chat", json={"question": ""})
        assert resp.status_code == 422
