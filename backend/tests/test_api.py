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
