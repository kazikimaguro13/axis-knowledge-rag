"""Parse [N] inline citation markers in RAG output.

The LLM is asked to emit ``[N]`` (1-indexed, matching the order of the
sources list) after claims it draws from a source. This module:

* normalizes the marker syntax (``[1, 2]`` -> ``[1][2]``),
* strips markers that reference an N out of range (the LLM occasionally
  hallucinates indices beyond the source count — we don't want those
  bracket numbers to bleed through to end users),
* skips markers that fall inside Markdown code fences (```...``` and
  inline ``` ` ... ` ```) so things like ``x = arr[1]`` in a code block
  are not treated as citations (spec_039), and
* exposes ``extract_citations()`` for UIs that want offsets instead of
  the cleaned string.

The marker form is plain text on purpose — see ADR-020 for the reasoning.
"""

from __future__ import annotations

import logging
import re

_log = logging.getLogger(__name__)

# Match [N], [1, 2], or consecutive [1][2] (handled by repeated matches).
# A single N is at most 3 digits — guard against runaway matches like [9999999].
_RE_MARKER = re.compile(r"\[(\d{1,3}(?:\s*,\s*\d{1,3})*)\]")

# Captures Markdown code regions whose contents must be skipped by the
# citation parser (spec_039):
# - fenced block: ``` (optionally followed by a language identifier) ... ```
# - inline span: `inline code`
# Nested fences are not part of the Markdown core spec and are not handled.
_RE_CODE_SPANS = re.compile(
    r"(?P<fenced>```[^\n]*\n.*?\n```)|(?P<inline>`[^`\n]+`)",
    re.DOTALL,
)


def _build_skip_ranges(text: str) -> list[tuple[int, int]]:
    """Return ``[start, end)`` ranges where citation markers should be ignored.

    The ranges cover Markdown code fences and inline code spans.
    """
    return [(m.start(), m.end()) for m in _RE_CODE_SPANS.finditer(text)]


def _is_in_skip_range(pos: int, ranges: list[tuple[int, int]]) -> bool:
    return any(s <= pos < e for s, e in ranges)


def parse_and_validate_citations(
    text: str, *, n_sources: int
) -> tuple[str, set[int]]:
    """Return (cleaned_text, set_of_used_source_indices_0based).

    * Strips markers whose N is outside ``1..n_sources`` (logs a warning
      so we can monitor LLM compliance over time).
    * Canonicalises ``[1, 2]`` to ``[1][2]`` so the frontend parser only
      has one shape to deal with.
    * If every N in a marker is invalid, the marker is removed entirely.
    * Markers that fall inside Markdown code fences / inline code are
      preserved verbatim (treated as literal text, not citations).
    """
    used: set[int] = set()
    skip_ranges = _build_skip_ranges(text)

    def _replace(m: re.Match[str]) -> str:
        if _is_in_skip_range(m.start(), skip_ranges):
            return m.group(0)
        nums_str = m.group(1)
        nums = [int(x.strip()) for x in nums_str.split(",")]
        valid = [n for n in nums if 1 <= n <= n_sources]
        invalid = [n for n in nums if n not in valid]
        if invalid:
            _log.warning(
                "citation out of range: %s (n_sources=%d)", invalid, n_sources
            )
        if not valid:
            return ""
        used.update(n - 1 for n in valid)
        return "".join(f"[{n}]" for n in valid)

    cleaned = _RE_MARKER.sub(_replace, text)
    return cleaned, used


def extract_citations(text: str) -> list[tuple[int, int, int]]:
    """Return ``(start, end, n_1based)`` triples for each marker.

    When a marker bundles multiple numbers (``[1, 2]``), each number gets
    the same ``(start, end)`` span — callers can decide whether to split
    the marker visually or leave it grouped. Markers inside Markdown code
    fences or inline code spans are skipped (spec_039).
    """
    out: list[tuple[int, int, int]] = []
    skip_ranges = _build_skip_ranges(text)
    for m in _RE_MARKER.finditer(text):
        if _is_in_skip_range(m.start(), skip_ranges):
            continue
        nums_str = m.group(1)
        for x in nums_str.split(","):
            try:
                n = int(x.strip())
            except ValueError:
                continue
            out.append((m.start(), m.end(), n))
    return out
