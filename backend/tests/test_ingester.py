"""Tests for backend.src.ingester (DUMMY mode only — no API key required)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import frontmatter
import pytest

from backend.src import ingester as ingester_mod
from backend.src.ingester import (
    Ingester,
    _next_doc_id,
    _scan_knowledge_dir,
    _strip_code_fence,
    render_markdown,
)
from backend.src.ingester_schemas import IngestOptions, IngestResult


@pytest.fixture
def empty_knowledge_dir(tmp_path: Path) -> Path:
    d = tmp_path / "knowledge_empty"
    d.mkdir()
    return d


@pytest.fixture
def populated_knowledge_dir(tmp_path: Path) -> Path:
    d = tmp_path / "knowledge_pop"
    d.mkdir()
    for n in range(1, 11):  # doc_001 .. doc_010
        (d / f"doc_{n:03d}.md").write_text(
            f"---\nid: doc_{n:03d}\ntitle: Existing {n}\naxes:\n  category: メモ\nrefs: []\n---\nBody {n}.\n",
            encoding="utf-8",
        )
    return d


def test_next_doc_id_empty_dir(empty_knowledge_dir: Path) -> None:
    assert _next_doc_id(empty_knowledge_dir) == "doc_001"


def test_next_doc_id_missing_dir(tmp_path: Path) -> None:
    assert _next_doc_id(tmp_path / "does_not_exist") == "doc_001"


def test_next_doc_id_increments(populated_knowledge_dir: Path) -> None:
    assert _next_doc_id(populated_knowledge_dir) == "doc_011"


def test_dummy_mode_produces_valid_result(empty_knowledge_dir: Path) -> None:
    ingester = Ingester(force_dummy=True)
    assert ingester.is_dummy is True
    opts = IngestOptions(knowledge_dir=str(empty_knowledge_dir))
    result = ingester.ingest("これはテスト用の生メモ本文です。ある程度の長さを持たせます。", opts)
    assert isinstance(result, IngestResult)
    assert result.id == "doc_001"
    assert len(result.body) >= 20
    assert "category" in result.axes


def test_dummy_mode_is_deterministic(empty_knowledge_dir: Path) -> None:
    ingester = Ingester(force_dummy=True)
    opts = IngestOptions(knowledge_dir=str(empty_knowledge_dir))
    raw = "決定論的なテキスト入力サンプル。同じ入力なら同じ出力になる。"
    a = ingester.ingest(raw, opts)
    b = ingester.ingest(raw, opts)
    assert a.title == b.title  # hash-derived → same input ⇒ same title


def test_render_markdown_round_trip(empty_knowledge_dir: Path) -> None:
    ingester = Ingester(force_dummy=True)
    opts = IngestOptions(knowledge_dir=str(empty_knowledge_dir))
    result = ingester.ingest("ラウンドトリップ用のサンプル本文を渡す。最低 20 文字。", opts)
    md = render_markdown(result)
    post = frontmatter.loads(md)
    assert post["id"] == result.id
    assert post["title"] == result.title
    assert dict(post["axes"]) == result.axes
    assert list(post["tags"]) == result.tags
    assert post.content.strip() == result.body.strip()


def test_render_markdown_starts_with_frontmatter(empty_knowledge_dir: Path) -> None:
    ingester = Ingester(force_dummy=True)
    opts = IngestOptions(knowledge_dir=str(empty_knowledge_dir))
    result = ingester.ingest("先頭が YAML frontmatter になっていることを確認するサンプル。", opts)
    md = render_markdown(result)
    assert md.startswith("---\n")
    assert "\n---\n\n" in md


def test_ingest_result_rejects_invalid_ref() -> None:
    with pytest.raises(ValueError):
        IngestResult(
            id="doc_999",
            title="title",
            axes={"category": "メモ"},
            tags=[],
            refs=["not_a_doc_id"],  # must start with doc_
            body="body content long enough to pass validation",
        )


def test_ingest_result_rejects_bad_id_pattern() -> None:
    with pytest.raises(ValueError):
        IngestResult(
            id="document_001",
            title="title",
            axes={"category": "メモ"},
            tags=[],
            refs=[],
            body="body content long enough to pass validation",
        )


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("```json\n{\"a\":1}\n```", '{"a":1}'),
        ("```\n{\"a\":1}\n```", '{"a":1}'),
        ('{"a":1}', '{"a":1}'),
        ("  {\"a\":1}  ", '{"a":1}'),
    ],
)
def test_strip_code_fence(raw: str, expected: str) -> None:
    assert _strip_code_fence(raw) == expected


# ---------------------------------------------------------------------------
# spec_026: single-scan + retry behaviour
# ---------------------------------------------------------------------------


def test_scan_knowledge_dir_single_load_directory_call(
    populated_knowledge_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`_scan_knowledge_dir` must call `load_directory` exactly once.

    Pre-spec_026 path used `_next_doc_id` + `_existing_doc_ids` separately,
    which together invoked `load_directory` twice per ingest.
    """
    call_count = 0
    original = ingester_mod.load_directory

    def counting(dir_path, **kw):
        nonlocal call_count
        call_count += 1
        return original(dir_path, **kw)

    monkeypatch.setattr(ingester_mod, "load_directory", counting)
    next_id, existing = _scan_knowledge_dir(populated_knowledge_dir)
    assert call_count == 1
    assert next_id == "doc_011"
    assert set(existing) == {f"doc_{n:03d}" for n in range(1, 11)}


def test_ingest_calls_load_directory_once(
    populated_knowledge_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: a single ingest() should hit load_directory only once."""
    call_count = 0
    original = ingester_mod.load_directory

    def counting(dir_path, **kw):
        nonlocal call_count
        call_count += 1
        return original(dir_path, **kw)

    monkeypatch.setattr(ingester_mod, "load_directory", counting)
    ingester = Ingester(force_dummy=True)
    opts = IngestOptions(knowledge_dir=str(populated_knowledge_dir))
    ingester.ingest("Body content for ingest, long enough for validation.", opts)
    assert call_count == 1


def test_next_doc_id_back_compat_wrapper(populated_knowledge_dir: Path) -> None:
    """`_next_doc_id` still returns the same value via `_scan_knowledge_dir`."""
    assert _next_doc_id(populated_knowledge_dir) == "doc_011"


def _fake_response(text: str) -> SimpleNamespace:
    return SimpleNamespace(content=[SimpleNamespace(text=text)])


def _valid_payload(next_id: str = "doc_001") -> str:
    return json.dumps(
        {
            "id": next_id,
            "title": "リトライ成功サンプル",
            "axes": {"category": "メモ"},
            "tags": ["retry", "auto"],
            "refs": [],
            "body": "リトライ後に返ってきた本文。最低 20 文字以上を確保する。",
        },
        ensure_ascii=False,
    )


def _make_ingester_with_mock_client(responses: list[str]) -> tuple[Ingester, list[str]]:
    """Construct an Ingester whose Claude client replays the given responses."""
    ingester = Ingester.__new__(Ingester)
    ingester._model = "mock-model"
    ingester._use_dummy = False
    sent_messages: list[str] = []
    iterator = iter(responses)

    class _Messages:
        def create(self, *, model, max_tokens, system, messages):
            sent_messages.append(messages[0]["content"])
            return _fake_response(next(iterator))

    ingester._client = SimpleNamespace(messages=_Messages())
    return ingester, sent_messages


def test_retry_succeeds_on_second_attempt(empty_knowledge_dir: Path) -> None:
    """First response is non-JSON; second response is valid → retry should succeed."""
    ingester, sent_messages = _make_ingester_with_mock_client(
        ["this is not JSON", _valid_payload("doc_001")]
    )
    opts = IngestOptions(knowledge_dir=str(empty_knowledge_dir), retry_count=2)
    result = ingester.ingest("retry sample body sufficiently long for validation.", opts)
    assert result.id == "doc_001"
    assert len(sent_messages) == 2
    # Second prompt must include the previous-attempt feedback block.
    assert "previous_attempt_failed" in sent_messages[1]
    assert "previous_attempt_failed" not in sent_messages[0]


def test_retry_exhausts_and_raises(empty_knowledge_dir: Path) -> None:
    """If all attempts fail, a RuntimeError with attempt count is raised."""
    ingester, sent_messages = _make_ingester_with_mock_client(
        ["nope", "still bad", "garbage"]
    )
    opts = IngestOptions(knowledge_dir=str(empty_knowledge_dir), retry_count=2)
    with pytest.raises(RuntimeError, match="after 3 attempts"):
        ingester.ingest("retry exhaustion sample body content here.", opts)
    assert len(sent_messages) == 3


def test_retry_count_zero_disables_retry(empty_knowledge_dir: Path) -> None:
    """retry_count=0 means a single attempt and no retry on failure."""
    ingester, sent_messages = _make_ingester_with_mock_client(
        ["not JSON", _valid_payload("doc_001")]  # 2nd should never be consumed
    )
    opts = IngestOptions(knowledge_dir=str(empty_knowledge_dir), retry_count=0)
    with pytest.raises(RuntimeError, match="after 1 attempts"):
        ingester.ingest("retry disabled sample body content here.", opts)
    assert len(sent_messages) == 1
