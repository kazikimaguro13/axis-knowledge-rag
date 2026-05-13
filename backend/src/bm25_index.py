"""BM25 keyword index for hybrid search.

Builds an in-memory BM25 (Okapi) index over normalized document bodies.
Tokenization is character n-gram (n=1, 2) on normalized text — avoids
the morphological analyzer dependency while still being usable for
Japanese (full-word vocabulary matching).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from backend.src.normalizer import Normalizer

logger = logging.getLogger(__name__)


def _tokenize(text: str) -> list[str]:
    """Character n-gram tokenizer (n=1, 2) over already-normalized text.

    Examples:
        "あいう" -> ["あ", "い", "う", "あい", "いう"]
    """
    if not text:
        return []
    tokens: list[str] = []
    tokens.extend(text)  # n=1
    for i in range(len(text) - 1):
        tokens.append(text[i : i + 2])  # n=2
    return tokens


@dataclass
class BM25Index:
    """In-memory BM25 index over a fixed corpus."""

    doc_ids: list[str]
    normalizer: Normalizer
    _model: BM25Okapi

    @classmethod
    def build(
        cls, docs: list[tuple[str, str]], normalizer: Normalizer
    ) -> BM25Index:
        """Build from `(doc_id, normalized_body)` pairs.

        The body should already be normalized (the same Normalizer that the
        index uses for queries) so that tokens match consistently.
        """
        ids = [d[0] for d in docs]
        tokenized = [_tokenize(d[1]) for d in docs]
        if not tokenized:
            tokenized = [[""]]  # rank_bm25 needs non-empty corpus
        model = BM25Okapi(tokenized)
        logger.info("BM25Index built (n_docs=%d)", len(ids))
        return cls(doc_ids=ids, normalizer=normalizer, _model=model)

    def score(self, query: str) -> dict[str, float]:
        """Return `{doc_id: bm25_score}` for the query.

        The query is normalized via `self.normalizer` then tokenized with
        the same n-gram scheme as the corpus. Raw BM25 scores are min-max
        normalized to `[0, 1]` so they can be summed with cosine similarity.
        """
        q_tokens = _tokenize(self.normalizer(query))
        if not q_tokens:
            return {}
        if not self.doc_ids:
            return {}
        scores = self._model.get_scores(q_tokens)
        if not len(scores):
            return {}
        s_min = float(scores.min())
        s_max = float(scores.max())
        if s_max - s_min < 1e-9:
            return {d: 0.0 for d in self.doc_ids}
        norm_scores = (scores - s_min) / (s_max - s_min)
        return {
            d: float(s)
            for d, s in zip(self.doc_ids, norm_scores, strict=True)
        }

    def __len__(self) -> int:
        return len(self.doc_ids)
