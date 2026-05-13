"""Japanese-aware text normalization.

NFKC + カタカナ→ひらがな + lowercase を組み合わせ、検索クエリと
インデックス対象テキストを揃える。LangChain / 外部ライブラリ非依存。
"""

import logging
import unicodedata
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# カタカナブロック (U+30A1〜U+30F6) → ひらがな (U+3041〜U+3096) のシフト量
_KATAKANA_START = 0x30A1
_KATAKANA_END = 0x30F6
_HIRAGANA_START = 0x3041


def _katakana_to_hiragana(text: str) -> str:
    out: list[str] = []
    for ch in text:
        cp = ord(ch)
        if _KATAKANA_START <= cp <= _KATAKANA_END:
            out.append(chr(cp - _KATAKANA_START + _HIRAGANA_START))
        else:
            out.append(ch)
    return "".join(out)


@dataclass(frozen=True)
class NormalizerOptions:
    nfkc: bool = True
    katakana_to_hiragana: bool = True
    lowercase: bool = True


def normalize_text(text: str, options: NormalizerOptions | None = None) -> str:
    opts = options or NormalizerOptions()
    s = text
    if opts.nfkc:
        s = unicodedata.normalize("NFKC", s)
    if opts.katakana_to_hiragana:
        s = _katakana_to_hiragana(s)
    if opts.lowercase:
        s = s.lower()
    return s


class Normalizer:
    """Stateful normalizer driven by config.yml `normalization` section."""

    def __init__(self, options: NormalizerOptions | None = None) -> None:
        self._opts = options or NormalizerOptions()

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "Normalizer":
        n = config.get("normalization", {}) or {}
        return cls(
            NormalizerOptions(
                nfkc=bool(n.get("nfkc", True)),
                katakana_to_hiragana=bool(n.get("katakana_to_hiragana", True)),
                lowercase=bool(n.get("lowercase", True)),
            )
        )

    @classmethod
    def identity(cls) -> "Normalizer":
        """A pass-through normalizer (all transformations disabled).

        Useful in tests where the input is already in canonical form and
        any normalization would obscure the assertions.
        """
        return cls(NormalizerOptions(nfkc=False, katakana_to_hiragana=False, lowercase=False))

    def __call__(self, text: str) -> str:
        return normalize_text(text, self._opts)

    @property
    def options(self) -> NormalizerOptions:
        return self._opts
