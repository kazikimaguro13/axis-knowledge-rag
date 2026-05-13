"""Tests for backend.src.marker --- 20+ cases."""

import sys
import os
import tempfile
import inspect
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.src.marker import (
    MarkerBlock,
    MarkerError,
    extract_blocks,
    strip_blocks,
    update_block,
    validate_balance,
)


def _b(name, content):
    return (
        f"<!-- AUTO_GENERATED_START: {name} -->\n"
        f"{content}\n"
        f"<!-- AUTO_GENERATED_END: {name} -->"
    )


def test_extract_zero_blocks():
    assert extract_blocks("No markers here.") == []


def test_extract_single_block():
    text = "before\n" + _b("summary", "hello") + "\nafter"
    blocks = extract_blocks(text)
    assert len(blocks) == 1
    assert blocks[0].name == "summary"
    assert blocks[0].content == "hello"
    assert "AUTO_GENERATED_START" in blocks[0].raw_full


def test_extract_multiple_blocks():
    text = _b("summary", "s") + "\n\n" + _b("faq", "q")
    blocks = extract_blocks(text)
    assert len(blocks) == 2
    assert blocks[0].name == "summary"
    assert blocks[1].name == "faq"


def test_extract_multiline_content():
    content = "line1\nline2\nline3"
    assert extract_blocks(_b("notes", content))[0].content == content


def test_extract_preserves_human_text():
    human = "# My Doc\n\nHuman text here.\n\n"
    text = human + _b("summary", "AI summary") + "\n"
    blocks = extract_blocks(text)
    assert len(blocks) == 1
    assert "Human text" not in blocks[0].content


def test_extract_name_hyphen_underscore():
    text = _b("my-block_v2", "content")
    assert extract_blocks(text)[0].name == "my-block_v2"


def test_update_existing_block():
    text = "intro\n" + _b("summary", "old content") + "\nfooter\n"
    result = update_block(text, "summary", "new content")
    assert "new content" in result
    assert "old content" not in result
    assert "intro" in result and "footer" in result


def test_update_preserves_other_blocks():
    text = _b("summary", "s") + "\n\n" + _b("faq", "f") + "\n"
    result = update_block(text, "summary", "new summary")
    blocks = extract_blocks(result)
    assert len(blocks) == 2
    faq = next(b for b in blocks if b.name == "faq")
    assert faq.content == "f"


def test_update_replaces_only_first():
    text = _b("summary", "first") + "\n\n" + _b("summary", "second") + "\n"
    result = update_block(text, "summary", "updated")
    assert result.count("updated") == 1
    assert "second" in result


def test_update_strips_trailing_newlines():
    text = _b("summary", "old") + "\n"
    result = update_block(text, "summary", "new\n\n")
    assert extract_blocks(result)[0].content == "new"


def test_update_appends_when_absent():
    text = "# Doc\n\nsome content\n"
    result = update_block(text, "summary", "AI generated")
    blocks = extract_blocks(result)
    assert len(blocks) == 1
    assert blocks[0].name == "summary"
    assert "# Doc" in result


def test_update_append_no_trailing_newline():
    result = update_block("content", "x", "y")
    assert result.startswith("content\n\n<!-- AUTO_GENERATED_START: x -->")


def test_update_append_single_newline():
    result = update_block("content\n", "x", "y")
    assert result.startswith("content\n\n<!-- AUTO_GENERATED_START: x -->")


def test_update_append_double_newline():
    result = update_block("content\n\n", "x", "y")
    assert result.startswith("content\n\n<!-- AUTO_GENERATED_START: x -->")


def test_update_invalid_name_at_sign():
    try:
        update_block("text", "bad@name", "content")
        assert False
    except MarkerError:
        pass


def test_update_invalid_name_space():
    try:
        update_block("text", "bad name", "content")
        assert False
    except MarkerError:
        pass


def test_strip_removes_all_blocks():
    text = "before\n" + _b("a", "A") + "\nmiddle\n" + _b("b", "B") + "\nafter\n"
    result = strip_blocks(text)
    assert "AUTO_GENERATED" not in result
    assert "before" in result and "middle" in result and "after" in result


def test_strip_no_blocks():
    text = "just human text\n"
    assert strip_blocks(text) == text


def test_strip_preserves_human_content():
    human = "# Title\n\nHuman paragraph.\n\n"
    text = human + _b("summary", "AI") + "\n"
    result = strip_blocks(text)
    assert "Human paragraph" in result
    assert "AI" not in result


def test_validate_balanced():
    assert validate_balance(_b("summary", "ok") + "\n") == []


def test_validate_start_only():
    text = "<!-- AUTO_GENERATED_START: summary -->\ncontent\n"
    errs = validate_balance(text)
    assert len(errs) >= 1 and any("mismatch" in e.lower() for e in errs)


def test_validate_end_only():
    text = "content\n<!-- AUTO_GENERATED_END: summary -->\n"
    assert len(validate_balance(text)) >= 1


def test_validate_name_mismatch():
    text = "<!-- AUTO_GENERATED_START: foo -->\ncontent\n<!-- AUTO_GENERATED_END: bar -->\n"
    assert len(validate_balance(text)) >= 1


def test_validate_multiple_balanced():
    text = _b("a", "1") + "\n" + _b("b", "2") + "\n"
    assert validate_balance(text) == []


def test_nested_dotall_outer_wins():
    inner = "<!-- AUTO_GENERATED_START: inner -->\nINNER\n<!-- AUTO_GENERATED_END: inner -->"
    text = f"<!-- AUTO_GENERATED_START: outer -->\n{inner}\n<!-- AUTO_GENERATED_END: outer -->\n"
    blocks = extract_blocks(text)
    assert len(blocks) == 1
    assert blocks[0].name == "outer"
    assert "inner" in blocks[0].content


def test_crlf_normalize():
    text = "line1\r\n" + _b("summary", "old").replace("\n", "\r\n") + "\r\nline2\r\n"
    normalized = text.replace("\r\n", "\n")
    result = update_block(normalized, "summary", "new")
    assert "\r\n" not in result
    assert "new" in result


def test_cli_list(tmp_path):
    import io
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


def test_cli_validate_ok(tmp_path):
    import io
    f = tmp_path / "doc.md"
    f.write_text(_b("x", "y") + "\n", encoding="utf-8")
    from backend.src.marker import _main
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    code = _main(["marker", str(f), "--validate"])
    output = sys.stdout.getvalue()
    sys.stdout = old_stdout
    assert code == 0 and "Balanced" in output


def test_cli_update_writes_file(tmp_path):
    f = tmp_path / "doc.md"
    f.write_text("# Doc\n\n" + _b("summary", "old") + "\n", encoding="utf-8")
    from backend.src.marker import _main
    code = _main(["marker", str(f), "--update", "--name", "summary", "--content", "new"])
    assert code == 0
    content = f.read_text(encoding="utf-8")
    assert "new" in content and "old" not in content


def test_cli_strip_writes_file(tmp_path):
    f = tmp_path / "doc.md"
    f.write_text("human\n" + _b("summary", "AI") + "\n", encoding="utf-8")
    from backend.src.marker import _main
    code = _main(["marker", str(f), "--strip"])
    assert code == 0
    content = f.read_text(encoding="utf-8")
    assert "AUTO_GENERATED" not in content and "human" in content


def test_cli_file_not_found(tmp_path):
    import io
    from backend.src.marker import _main
    old_stderr = sys.stderr
    sys.stderr = io.StringIO()
    code = _main(["marker", str(tmp_path / "nonexistent.md"), "--list"])
    sys.stderr = old_stderr
    assert code == 1


if __name__ == "__main__":
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    failed = 0
    for name, t in tests:
        try:
            sig = inspect.signature(t)
            if sig.parameters:
                with tempfile.TemporaryDirectory() as td:
                    t(Path(td))
            else:
                t()
            print(f"  PASS  {name}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {name}: {e}")
            failed += 1
    total = passed + failed
    print(f"\n{total} tests --- {passed} passed, {failed} failed")
    import sys as _sys
    _sys.exit(0 if failed == 0 else 1)