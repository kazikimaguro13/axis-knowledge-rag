"""Tests for backend.src.marker --- 20+ cases."""

import io
import sys
from pathlib import Path

import pytest

from backend.src.marker import (
    MarkerError,
    extract_blocks,
    strip_blocks,
    update_block,
    validate_balance,
)


def _b(name: str, content: str) -> str:
    return (
        f"<!-- AUTO_GENERATED_START: {name} -->\n"
        f"{content}\n"
        f"<!-- AUTO_GENERATED_END: {name} -->"
    )


def test_extract_zero_blocks() -> None:
    assert extract_blocks("No markers here.") == []


def test_extract_single_block() -> None:
    text = "before\n" + _b("summary", "hello") + "\nafter"
    blocks = extract_blocks(text)
    assert len(blocks) == 1
    assert blocks[0].name == "summary"
    assert blocks[0].content == "hello"
    assert "AUTO_GENERATED_START" in blocks[0].raw_full


def test_extract_multiple_blocks() -> None:
    text = _b("summary", "s") + "\n\n" + _b("faq", "q")
    blocks = extract_blocks(text)
    assert len(blocks) == 2
    assert blocks[0].name == "summary"
    assert blocks[1].name == "faq"


def test_extract_multiline_content() -> None:
    content = "line1\nline2\nline3"
    assert extract_blocks(_b("notes", content))[0].content == content


def test_extract_preserves_human_text() -> None:
    human = "# My Doc\n\nHuman text here.\n\n"
    text = human + _b("summary", "AI summary") + "\n"
    blocks = extract_blocks(text)
    assert len(blocks) == 1
    assert "Human text" not in blocks[0].content


def test_extract_name_hyphen_underscore() -> None:
    text = _b("my-block_v2", "content")
    assert extract_blocks(text)[0].name == "my-block_v2"


def test_update_existing_block() -> None:
    text = "intro\n" + _b("summary", "old content") + "\nfooter\n"
    result = update_block(text, "summary", "new content")
    assert "new content" in result
    assert "old content" not in result
    assert "intro" in result and "footer" in result


def test_update_preserves_other_blocks() -> None:
    text = _b("summary", "s") + "\n\n" + _b("faq", "f") + "\n"
    result = update_block(text, "summary", "new summary")
    blocks = extract_blocks(result)
    assert len(blocks) == 2
    faq = next(b for b in blocks if b.name == "faq")
    assert faq.content == "f"


def test_update_replaces_only_first() -> None:
    text = _b("summary", "first") + "\n\n" + _b("summary", "second") + "\n"
    result = update_block(text, "summary", "updated")
    assert result.count("updated") == 1
    assert "second" in result


def test_update_strips_trailing_newlines() -> None:
    text = _b("summary", "old") + "\n"
    result = update_block(text, "summary", "new\n\n")
    assert extract_blocks(result)[0].content == "new"


def test_update_appends_when_absent() -> None:
    text = "# Doc\n\nsome content\n"
    result = update_block(text, "summary", "AI generated")
    blocks = extract_blocks(result)
    assert len(blocks) == 1
    assert blocks[0].name == "summary"
    assert "# Doc" in result


@pytest.mark.parametrize(
    "existing,expected_prefix",
    [
        ("content", "content\n\n<!-- AUTO_GENERATED_START: x -->"),
        ("content\n", "content\n\n<!-- AUTO_GENERATED_START: x -->"),
        ("content\n\n", "content\n\n<!-- AUTO_GENERATED_START: x -->"),
    ],
)
def test_update_append_normalizes_newlines(existing: str, expected_prefix: str) -> None:
    result = update_block(existing, "x", "y")
    assert result.startswith(expected_prefix)


@pytest.mark.parametrize("invalid_name", ["bad@name", "bad name"])
def test_update_invalid_name_raises(invalid_name: str) -> None:
    with pytest.raises(MarkerError):
        update_block("text", invalid_name, "content")


def test_strip_removes_all_blocks() -> None:
    text = "before\n" + _b("a", "A") + "\nmiddle\n" + _b("b", "B") + "\nafter\n"
    result = strip_blocks(text)
    assert "AUTO_GENERATED" not in result
    assert "before" in result and "middle" in result and "after" in result


def test_strip_no_blocks() -> None:
    text = "just human text\n"
    assert strip_blocks(text) == text


def test_strip_preserves_human_content() -> None:
    human = "# Title\n\nHuman paragraph.\n\n"
    text = human + _b("summary", "AI") + "\n"
    result = strip_blocks(text)
    assert "Human paragraph" in result
    assert "AI" not in result


def test_validate_balanced() -> None:
    assert validate_balance(_b("summary", "ok") + "\n") == []


def test_validate_start_only() -> None:
    text = "<!-- AUTO_GENERATED_START: summary -->\ncontent\n"
    errs = validate_balance(text)
    assert len(errs) >= 1 and any("mismatch" in e.lower() for e in errs)


def test_validate_end_only() -> None:
    text = "content\n<!-- AUTO_GENERATED_END: summary -->\n"
    assert len(validate_balance(text)) >= 1


def test_validate_name_mismatch() -> None:
    text = "<!-- AUTO_GENERATED_START: foo -->\ncontent\n<!-- AUTO_GENERATED_END: bar -->\n"
    assert len(validate_balance(text)) >= 1


def test_validate_multiple_balanced() -> None:
    text = _b("a", "1") + "\n" + _b("b", "2") + "\n"
    assert validate_balance(text) == []


def test_nested_dotall_outer_wins() -> None:
    inner = "<!-- AUTO_GENERATED_START: inner -->\nINNER\n<!-- AUTO_GENERATED_END: inner -->"
    text = f"<!-- AUTO_GENERATED_START: outer -->\n{inner}\n<!-- AUTO_GENERATED_END: outer -->\n"
    blocks = extract_blocks(text)
    assert len(blocks) == 1
    assert blocks[0].name == "outer"
    assert "inner" in blocks[0].content


def test_crlf_normalize() -> None:
    text = "line1\r\n" + _b("summary", "old").replace("\n", "\r\n") + "\r\nline2\r\n"
    normalized = text.replace("\r\n", "\n")
    result = update_block(normalized, "summary", "new")
    assert "\r\n" not in result
    assert "new" in result


def test_cli_list(tmp_path: Path) -> None:
    f = tmp_path / "doc.md"
    f.write_text("# Doc\n\n" + _b("summary", "AI summary") + "\n", encoding="utf-8")
    from backend.src.marker import _main

    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    code = _main(["marker", str(f), "--list"])
    output = sys.stdout.getvalue()
    sys.stdout = old_stdout
    assert code == 0
    assert "1 block(s)" in output and "summary" in output


def test_cli_validate_ok(tmp_path: Path) -> None:
    f = tmp_path / "doc.md"
    f.write_text(_b("x", "y") + "\n", encoding="utf-8")
    from backend.src.marker import _main

    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    code = _main(["marker", str(f), "--validate"])
    output = sys.stdout.getvalue()
    sys.stdout = old_stdout
    assert code == 0 and "Balanced" in output


def test_cli_update_writes_file(tmp_path: Path) -> None:
    f = tmp_path / "doc.md"
    f.write_text("# Doc\n\n" + _b("summary", "old") + "\n", encoding="utf-8")
    from backend.src.marker import _main

    code = _main(["marker", str(f), "--update", "--name", "summary", "--content", "new"])
    assert code == 0
    content = f.read_text(encoding="utf-8")
    assert "new" in content and "old" not in content


def test_cli_strip_writes_file(tmp_path: Path) -> None:
    f = tmp_path / "doc.md"
    f.write_text("human\n" + _b("summary", "AI") + "\n", encoding="utf-8")
    from backend.src.marker import _main

    code = _main(["marker", str(f), "--strip"])
    assert code == 0
    content = f.read_text(encoding="utf-8")
    assert "AUTO_GENERATED" not in content and "human" in content


def test_cli_file_not_found(tmp_path: Path) -> None:
    from backend.src.marker import _main

    old_stderr = sys.stderr
    sys.stderr = io.StringIO()
    code = _main(["marker", str(tmp_path / "nonexistent.md"), "--list"])
    sys.stderr = old_stderr
    assert code == 1
