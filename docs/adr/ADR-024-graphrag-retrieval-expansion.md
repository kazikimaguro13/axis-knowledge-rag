# ADR-024: GraphRAG — refs-driven retrieval expansion

- **Status**: Accepted
- **Date**: 2026-05-14
- **Spec**: spec_040

## Context

axis-knowledge-rag has stored a `refs: [doc_X, doc_Y]` list inside every
document's YAML frontmatter since day 1, but the field has only ever been
consumed by `integrity.py` (broken-ref / cycle reporting). At retrieval
time the rich human signal that "this document is conceptually adjacent
to those other documents" was thrown away.

Consequences in practice:
- A hit on `doc_005` (prompt-engineering memo) would *not* surface its
  companion `doc_006` (prompt-injection follow-up) even though both
  authors connected them explicitly through `refs:`.
- The chunk-level BM25 + vector hybrid is excellent at lexical/semantic
  overlap but blind to *editorial* relationships.
- Microsoft's GraphRAG line of work (2024–2025) made graph-augmented
  retrieval a recognised pattern; not having any graph layer felt like a
  noticeable gap relative to current OSS RAG stacks.

## Decision

Introduce a thin, in-memory `KnowledgeGraph` layer (`backend/src/graph.py`)
built once at FastAPI lifespan startup from the loaded frontmatter, and
expose a *single* opt-in expansion path in `SearchEngine.search()`:

1. Run the existing pipeline (parent-doc/file-level + BM25 + time decay)
   exactly as before.
2. When `graph_expand=True`, for the top 5 results call
   `graph.neighbors_within_hop(doc_id, hop=1, max_neighbors=10)` and
   append any not-yet-seen neighbours with `score = source.score × 0.7`.
3. Re-sort by score and return.

Backed by `networkx>=3.0` (DiGraph). Self-loops are silently skipped,
broken refs are logged + skipped, circular refs are allowed.

## Alternatives considered

(a) **Neo4j / dedicated graph DB** — rejected: a 7 MB Python library
plus a sidecar daemon for what is effectively ≤ 10 k edges. Doesn't fit
the local-first ethos.

(b) **ChromaDB metadata join** — rejected: Chroma does not have a graph
traversal operator, so BFS would be N round-trips with N=hop, slow even
at small scale.

(c) **In-process networkx** — chosen. Zero extra processes,
600 KB of pure Python, well-tested BFS / shortest-path primitives, and
the same library is convenient for the future PageRank / centrality
ideas (spec_041 candidates).

(d) **PageRank-weighted score blend instead of flat 0.7× decay** —
considered, deferred. Flat decay is a single-line knob with predictable
behaviour; PageRank introduces tuning surface (damping factor, blend
weight) that we would want to validate against RAGAS before shipping.

## Consequences

- New main-dep: `networkx>=3.0,<4` (~600 KB). Acceptable.
- Graph build is O(N+E) at startup, O(1) per neighbour query. With the
  10-doc example corpus this is sub-millisecond.
- `graph_expand` defaults to **false** at the API layer, so every
  pre-spec_040 client gets identical results. `config.yml`
  `graph.expand_on_search: true` can flip the default once we evaluate
  with RAGAS (spec_041 candidate).
- Result-set size can grow by up to `5 × max_neighbors` documents when
  expansion fires — callers that slice to `top_k` after the call still
  see at most `top_k`, but RAG context construction must be aware that
  more sources may now appear.
- Tested against the example corpus (`refs: doc_999`, a deliberate
  broken ref) to confirm warning-and-skip behaviour.
