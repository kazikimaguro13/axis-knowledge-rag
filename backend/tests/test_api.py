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


# ---------------------------------------------------------------------------
# spec_040: /api/graph + /api/graph/{id}/neighbors
# ---------------------------------------------------------------------------


def test_get_graph_returns_nodes_and_edges() -> None:
    with TestClient(app) as client:
        resp = client.get("/api/graph")
        assert resp.status_code == 200
        body = resp.json()
        assert "nodes" in body
        assert "edges" in body
        assert "stats" in body
        assert isinstance(body["nodes"], list)
        assert isinstance(body["edges"], list)
        assert {"nodes", "edges", "isolated", "weakly_connected_components"} <= set(
            body["stats"]
        )


def test_get_graph_filter_by_category() -> None:
    with TestClient(app) as client:
        full = client.get("/api/graph").json()
        filtered = client.get("/api/graph?axes_category=技術記事").json()
        assert len(filtered["nodes"]) <= len(full["nodes"])
        for n in filtered["nodes"]:
            assert str(n["axes"].get("category", "")) == "技術記事"


def test_get_neighbors_known_doc() -> None:
    """doc_001 in examples/knowledge is referenced by doc_002 and doc_004."""
    with TestClient(app) as client:
        resp = client.get("/api/graph/doc_001/neighbors?hop=1&max_neighbors=10")
        assert resp.status_code == 200
        body = resp.json()
        assert body["center"]["id"] == "doc_001"
        assert isinstance(body["neighbors"], list)
        # Direction defaults to "both", so doc_001 picks up its incoming refs.
        ids = {n["id"] for n in body["neighbors"]}
        assert ids  # at least one neighbour from the example corpus


def test_get_neighbors_unknown_doc_returns_404() -> None:
    with TestClient(app) as client:
        resp = client.get("/api/graph/does_not_exist_doc/neighbors")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# spec_049: direction query param (out / in / both)
# ---------------------------------------------------------------------------


def test_neighbors_direction_out_only() -> None:
    """doc_002 has refs:[doc_001] — direction=out should return only doc_001."""
    with TestClient(app) as client:
        resp = client.get("/api/graph/doc_002/neighbors?direction=out&hop=1")
        assert resp.status_code == 200
        ids = {n["id"] for n in resp.json()["neighbors"]}
        assert ids == {"doc_001"}


def test_neighbors_direction_in_only() -> None:
    """doc_001 is referenced by doc_002 / doc_004 / doc_007 — direction=in returns them."""
    with TestClient(app) as client:
        resp = client.get("/api/graph/doc_001/neighbors?direction=in&hop=1")
        assert resp.status_code == 200
        ids = {n["id"] for n in resp.json()["neighbors"]}
        assert {"doc_002", "doc_004", "doc_007"} <= ids
        # doc_001 has no outgoing refs, so nothing extra should leak in.
        assert all(i in {"doc_002", "doc_004", "doc_007"} for i in ids)


def test_neighbors_direction_both_default() -> None:
    """No direction param ⇒ both (backward-compat with pre-spec_049 callers)."""
    with TestClient(app) as client:
        no_param = client.get("/api/graph/doc_002/neighbors?hop=1").json()
        both = client.get("/api/graph/doc_002/neighbors?direction=both&hop=1").json()
        assert {n["id"] for n in no_param["neighbors"]} == {
            n["id"] for n in both["neighbors"]
        }


# ---------------------------------------------------------------------------
# spec_046: /api/ingest — browser-extension capture
# ---------------------------------------------------------------------------


def test_post_ingest_returns_saved_path(tmp_path) -> None:
    # Route the writer at a tmp dir so the suite never touches the real
    # ``examples/knowledge/`` corpus.
    from backend.src import api as api_module

    with TestClient(app) as client:
        api_module._state["knowledge_dir"] = str(tmp_path)
        resp = client.post(
            "/api/ingest",
            json={
                "url": "https://example.com/article",
                "title": "Sample Article",
                "body": "hello world",
                "selected_text": None,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["doc_id"].startswith("web_")
        saved = tmp_path / f"{body['doc_id']}.md"
        assert saved.exists()
        text = saved.read_text(encoding="utf-8")
        assert "Sample Article" in text
        assert "https://example.com/article" in text


def test_post_ingest_invalid_body_422() -> None:
    with TestClient(app) as client:
        # Missing required ``url`` field → FastAPI validation error.
        resp = client.post(
            "/api/ingest",
            json={"title": "x", "body": "y"},
        )
        assert resp.status_code == 422
        # Empty title (min_length=1) also rejected.
        resp2 = client.post(
            "/api/ingest",
            json={"url": "https://example.com", "title": "", "body": "y"},
        )
        assert resp2.status_code == 422


# ---------------------------------------------------------------------------
# spec_051 MID-1: AXIS_INGEST_TOKEN opt-in auth
# ---------------------------------------------------------------------------


def test_post_ingest_requires_token_when_env_set(tmp_path, monkeypatch) -> None:
    """When AXIS_INGEST_TOKEN is set, a request without (or with the wrong)
    X-Axis-Token header is rejected with 401."""
    from backend.src import api as api_module

    monkeypatch.setenv("AXIS_INGEST_TOKEN", "secret-abc-123")
    with TestClient(app) as client:
        api_module._state["knowledge_dir"] = str(tmp_path)
        # No header → 401
        resp = client.post(
            "/api/ingest",
            json={
                "url": "https://example.com/article",
                "title": "Sample",
                "body": "hello",
            },
        )
        assert resp.status_code == 401, resp.text
        # Wrong header → 401
        resp2 = client.post(
            "/api/ingest",
            headers={"X-Axis-Token": "wrong"},
            json={
                "url": "https://example.com/article",
                "title": "Sample",
                "body": "hello",
            },
        )
        assert resp2.status_code == 401


def test_post_ingest_passes_with_correct_token(tmp_path, monkeypatch) -> None:
    """Matching token in X-Axis-Token header → 200 + file persisted."""
    from backend.src import api as api_module

    monkeypatch.setenv("AXIS_INGEST_TOKEN", "secret-abc-123")
    with TestClient(app) as client:
        api_module._state["knowledge_dir"] = str(tmp_path)
        resp = client.post(
            "/api/ingest",
            headers={"X-Axis-Token": "secret-abc-123"},
            json={
                "url": "https://example.com/article",
                "title": "Sample",
                "body": "hello",
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["doc_id"].startswith("web_")


# ---------------------------------------------------------------------------
# spec_047: /api/feedback + /api/feedback/report
# ---------------------------------------------------------------------------


def test_post_feedback_records(tmp_path) -> None:
    from backend.src import api as api_module
    from backend.src.feedback import SqliteFeedbackStore

    with TestClient(app) as client:
        # Swap in a tmp-dir store so the test never touches ~/.axis_feedback.db.
        tmp_store = SqliteFeedbackStore(db_path=str(tmp_path / "fb.db"))
        api_module._state["feedback_store"] = tmp_store
        try:
            resp = client.post(
                "/api/feedback",
                json={
                    "query": "RAG とは?",
                    "doc_id": "doc_001",
                    "rating": 1,
                    "session_id": "sid_abc",
                },
            )
            assert resp.status_code == 200, resp.text
            assert "feedback_id" in resp.json()
            assert tmp_store.count() == 1
        finally:
            tmp_store.close()


def test_post_feedback_rating_validated() -> None:
    with TestClient(app) as client:
        # rating must be in [-1, 1]; 2 is rejected by Pydantic Field(ge=-1, le=1).
        resp = client.post(
            "/api/feedback",
            json={"query": "q", "doc_id": "d", "rating": 2},
        )
        assert resp.status_code == 422


def test_feedback_report_endpoint(tmp_path) -> None:
    from backend.src import api as api_module
    from backend.src.feedback import SqliteFeedbackStore

    with TestClient(app) as client:
        tmp_store = SqliteFeedbackStore(db_path=str(tmp_path / "fb.db"))
        api_module._state["feedback_store"] = tmp_store
        try:
            client.post(
                "/api/feedback",
                json={"query": "q1", "doc_id": "doc_x", "rating": -1},
            )
            resp = client.get("/api/feedback/report?days=7")
            assert resp.status_code == 200
            md = resp.json()["markdown"]
            assert "Feedback report" in md
            assert "doc_x" in md
        finally:
            tmp_store.close()


def test_feedback_disabled_returns_503() -> None:
    from backend.src import api as api_module

    with TestClient(app) as client:
        # Lifespan populated the store; null it out to simulate
        # config.feedback.enabled=false (which `make_feedback_store` maps to
        # `None`).
        prev = api_module._state.get("feedback_store")
        api_module._state["feedback_store"] = None
        try:
            resp = client.post(
                "/api/feedback",
                json={"query": "q", "doc_id": "d", "rating": 1},
            )
            assert resp.status_code == 503
            resp2 = client.get("/api/feedback/report")
            assert resp2.status_code == 503
        finally:
            api_module._state["feedback_store"] = prev
