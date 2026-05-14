"""Tests for backend.src._citations parser."""

from backend.src._citations import extract_citations, parse_and_validate_citations


def test_basic_single_citation() -> None:
    text = "RAG is great[1]. BM25 helps[2]."
    cleaned, used = parse_and_validate_citations(text, n_sources=2)
    assert cleaned == "RAG is great[1]. BM25 helps[2]."
    assert used == {0, 1}


def test_canonicalises_comma_separated_marker() -> None:
    text = "Both true[1, 2]."
    cleaned, used = parse_and_validate_citations(text, n_sources=2)
    assert cleaned == "Both true[1][2]."
    assert used == {0, 1}


def test_consecutive_markers_pass_through_unchanged() -> None:
    text = "Yes[1][2]."
    cleaned, used = parse_and_validate_citations(text, n_sources=2)
    assert cleaned == "Yes[1][2]."
    assert used == {0, 1}


def test_out_of_range_marker_is_stripped() -> None:
    text = "Bad[3] good[1]."
    cleaned, used = parse_and_validate_citations(text, n_sources=2)
    assert cleaned == "Bad good[1]."
    assert used == {0}


def test_partially_invalid_marker_keeps_valid_part() -> None:
    text = "Mixed[1, 9]."
    cleaned, used = parse_and_validate_citations(text, n_sources=2)
    assert cleaned == "Mixed[1]."
    assert used == {0}


def test_no_citations_passthrough() -> None:
    text = "No markers here."
    cleaned, used = parse_and_validate_citations(text, n_sources=2)
    assert cleaned == "No markers here."
    assert used == set()


def test_zero_index_is_invalid() -> None:
    # [0] is out of range — 1-indexed scheme.
    text = "Weird[0] but ok[1]."
    cleaned, used = parse_and_validate_citations(text, n_sources=2)
    assert cleaned == "Weird but ok[1]."
    assert used == {0}


def test_extract_offsets_basic() -> None:
    text = "A[1] B[2,3]."
    offsets = extract_citations(text)
    # [1] starts at offset 1, ends at 4
    assert (1, 4, 1) in offsets
    # [2,3] starts at offset 6, ends at 11 — both 2 and 3 share the same span
    assert (6, 11, 2) in offsets
    assert (6, 11, 3) in offsets


def test_extract_offsets_no_markers() -> None:
    assert extract_citations("plain text") == []


def test_unused_indices_not_in_used_set() -> None:
    text = "Only one cited[1]."
    cleaned, used = parse_and_validate_citations(text, n_sources=5)
    assert cleaned == "Only one cited[1]."
    assert used == {0}


def test_marker_with_whitespace_in_csv() -> None:
    text = "Spaced[1 ,  2]."
    cleaned, used = parse_and_validate_citations(text, n_sources=2)
    assert cleaned == "Spaced[1][2]."
    assert used == {0, 1}


def test_all_invalid_marker_disappears_entirely() -> None:
    text = "Lies[7, 8, 9]."
    cleaned, used = parse_and_validate_citations(text, n_sources=3)
    assert cleaned == "Lies."
    assert used == set()


def test_n_sources_zero_strips_everything() -> None:
    text = "Anything[1] goes[2]."
    cleaned, used = parse_and_validate_citations(text, n_sources=0)
    assert cleaned == "Anything goes."
    assert used == set()
