"""Project-wide configuration loaded from environment / .env."""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

COLLECTION_NAME = "axis_knowledge"


@dataclass(frozen=True)
class Settings:
    """Runtime settings.

    Values are sourced from environment variables (or .env if present).
    """

    anthropic_api_key: str | None = os.getenv("ANTHROPIC_API_KEY")
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY")
    chroma_db_path: Path = Path(os.getenv("CHROMA_DB_PATH", "./.chromadb"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")


def configure_logging(level: str | None = None) -> None:
    """Configure root logger with project-standard format."""
    logging.basicConfig(
        level=level or Settings().log_level,
        format="[%(levelname)s] %(name)s: %(message)s",
    )


settings = Settings()


def load_axes_config(path: Path | None = None) -> dict:
    """Load axes definition from config.yml."""
    import yaml

    config_path = path or Path("./config.yml")
    if not config_path.exists():
        return {"axes": []}
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {"axes": []}


# ---------------------------------------------------------------------------
# spec_031: parent-document retrieval settings
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParentDocConfig:
    """Settings for the small-to-big (parent / child) retrieval path."""

    enabled: bool = True
    chunk_strategy: str = "h2"  # currently only "h2" is implemented
    max_child_tokens: int = 256
    top_k_children: int = 20
    top_n_parents: int = 5
    storage: str = "sqlite"  # spec_037: "sqlite" (default) | "json" (legacy v0.7)


# ---------------------------------------------------------------------------
# spec_035: time-weighted decay settings
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TimeDecayConfig:
    """Settings for recency-boost via exponential half-life decay.

    default: enabled=False (opt-in). When enabled, newer docs get a slight
    score boost without fully overriding relevance ranking.
    """

    enabled: bool = False
    half_life_days: float = 180.0
    weight: float = 0.15
    date_field: str = "updated"  # frontmatter field name; "created" also works


@dataclass(frozen=True)
class RetrievalConfig:
    parent_doc: ParentDocConfig = field(default_factory=ParentDocConfig)
    time_decay: TimeDecayConfig = field(default_factory=TimeDecayConfig)


@dataclass(frozen=True)
class RAGConfig:
    context_max_chars: int = 8000


# ---------------------------------------------------------------------------
# spec_032: conversational RAG settings
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChatRewriterConfig:
    enabled: bool = True
    model: str = "gemini-2.5-flash"


# ---------------------------------------------------------------------------
# spec_036: chat session storage backend selection
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StorageConfig:
    """Backend selection for ``ConversationStore`` (spec_036).

    - ``backend="sqlite"`` (default): file-backed, survives restarts.
    - ``backend="memory"``: v0.7 in-memory dict; lost on restart, OK for tests.
    - ``backend="redis"``: requires ``pip install -e ".[redis]"``.
    """

    backend: str = "sqlite"  # "memory" | "sqlite" | "redis"
    sqlite_path: str = "~/.axis_chat.db"
    redis_url: str = "redis://localhost:6379/0"


@dataclass(frozen=True)
class ChatConfig:
    """Settings for the conversational ``/api/chat`` path."""

    enabled: bool = True
    max_history_turns: int = 6   # 6 turn = 12 messages kept in store
    ttl_seconds: int = 86400     # 24h since last access → evicted
    max_sessions: int = 100      # LRU cap
    rewriter: ChatRewriterConfig = field(default_factory=ChatRewriterConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)


# ---------------------------------------------------------------------------
# spec_040: knowledge graph (refs-driven) settings
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# spec_045: Ollama / Llama.cpp backend selection (embedder + generation)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OllamaConfig:
    """Connection settings for an Ollama backend (shared by embedder + gen)."""

    model: str = "bge-m3"
    url: str = "http://localhost:11434"


@dataclass(frozen=True)
class EmbedderConfig:
    """Selects which embedder backend ``make_embedder()`` builds.

    ``backend``: ``"gemini"`` (v0.8.1 default) | ``"ollama"`` | ``"dummy"``.
    ``ollama``: connection settings when ``backend="ollama"``. ``bge-m3`` is
    the default model (1024-dim, multilingual JP/EN).
    """

    backend: str = "gemini"
    ollama: OllamaConfig = field(default_factory=lambda: OllamaConfig(model="bge-m3"))


@dataclass(frozen=True)
class GenerationConfig:
    """Selects which generation backend ``make_generation_backend()`` builds.

    ``backend``: ``"claude"`` (v0.8.1 default) | ``"ollama"`` | ``"dummy"``.
    ``ollama``: connection settings when ``backend="ollama"``. ``llama3``
    is a sensible default; swap for ``llama3:70b`` / ``mistral`` etc. via
    ``config.yml``.
    """

    backend: str = "claude"
    ollama: OllamaConfig = field(default_factory=lambda: OllamaConfig(model="llama3"))


@dataclass(frozen=True)
class GraphConfig:
    """Settings for the refs-driven knowledge graph layer (spec_040).

    The graph is opt-in for retrieval expansion (default ``expand_on_search``
    is False) so existing search behaviour is unchanged unless callers
    explicitly request it. The /api/graph endpoints + 3D visualization
    are gated by ``enabled``.
    """

    enabled: bool = True
    default_hop: int = 1
    max_neighbors_per_query: int = 20
    expand_on_search: bool = False
    knowledge_dir: str = "./examples/knowledge"


# ---------------------------------------------------------------------------
# spec_047: active-learning feedback loop settings
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FeedbackConfig:
    """Settings for the 👍/👎 feedback store (spec_047).

    Defaults: enabled, file-backed SQLite at ``~/.axis_feedback.db``. Flip
    ``enabled`` to False to have ``/api/feedback`` return 503 — useful for
    deployments that route signals through a different observability path.
    """

    enabled: bool = True
    db_path: str = "~/.axis_feedback.db"


# ---------------------------------------------------------------------------
# spec_048: knowledge-gap detection settings
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GapConfig:
    """Settings for the knowledge-gap detection store (spec_048).

    Defaults: enabled, file-backed SQLite at ``~/.axis_gap.db``. Flip
    ``enabled`` to False to make the ``search.py`` / ``rag.py`` hooks
    no-op (zero added work on the hot path) and ``/api/gap/report``
    return 503. ``low_score_threshold`` is the cosine-blended top score
    below which a hit is considered "we kind of have it but probably
    not what they wanted" — 0.35 chosen to match the v0.8 RAGAS eval's
    "weak hit" band.
    """

    enabled: bool = True
    db_path: str = "~/.axis_gap.db"
    low_score_threshold: float = 0.35


@dataclass(frozen=True)
class AppConfig:
    """Aggregated runtime config (axes + retrieval + rag + chat + graph)."""

    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    rag: RAGConfig = field(default_factory=RAGConfig)
    chat: ChatConfig = field(default_factory=ChatConfig)
    graph: GraphConfig = field(default_factory=GraphConfig)
    # spec_045: Ollama / Llama.cpp backend selection (defaults preserve
    # v0.8.1 behaviour — Gemini for embedding, Claude for generation).
    embedder: EmbedderConfig = field(default_factory=EmbedderConfig)
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    # spec_047: 👍/👎 feedback store.
    feedback: FeedbackConfig = field(default_factory=FeedbackConfig)
    # spec_048: knowledge-gap detection store.
    gap: GapConfig = field(default_factory=GapConfig)


def load_app_config(path: Path | None = None) -> AppConfig:
    """Load full ``config.yml`` into the typed ``AppConfig`` (with defaults).

    Missing keys / missing file → all defaults. Unknown keys are ignored
    so older config files keep working.

    spec_042: After loading, ``EVAL_OVERRIDE_FLAG`` env var (if set) can
    override any dotted key in the result (used by ``run_abtest.py``).
    Format: ``"retrieval.time_decay.enabled=true;chat.enabled=false"``.
    """
    import yaml

    config_path = path or Path("./config.yml")
    if not config_path.exists():
        cfg = AppConfig()
    else:
        try:
            with open(config_path, encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
        except OSError:
            cfg = AppConfig()
        else:
            cfg = _build_app_config(raw)

    override = os.environ.get("EVAL_OVERRIDE_FLAG", "").strip()
    if override:
        cfg = _apply_override_flags(cfg, override)
    return cfg


def _build_app_config(raw: dict) -> AppConfig:
    """Convert raw yaml dict → typed AppConfig (defaults fill the gaps)."""
    retr_raw = (raw.get("retrieval") or {}) if isinstance(raw, dict) else {}
    pd_raw = (retr_raw.get("parent_doc") or {}) if isinstance(retr_raw, dict) else {}
    td_raw = (retr_raw.get("time_decay") or {}) if isinstance(retr_raw, dict) else {}
    rag_raw = (raw.get("rag") or {}) if isinstance(raw, dict) else {}
    chat_raw = (raw.get("chat") or {}) if isinstance(raw, dict) else {}
    rew_raw = (chat_raw.get("rewriter") or {}) if isinstance(chat_raw, dict) else {}
    store_raw = (chat_raw.get("storage") or {}) if isinstance(chat_raw, dict) else {}
    graph_raw = (raw.get("graph") or {}) if isinstance(raw, dict) else {}
    emb_raw = (raw.get("embedder") or {}) if isinstance(raw, dict) else {}
    emb_ollama_raw = (emb_raw.get("ollama") or {}) if isinstance(emb_raw, dict) else {}
    gen_raw = (raw.get("generation") or {}) if isinstance(raw, dict) else {}
    gen_ollama_raw = (gen_raw.get("ollama") or {}) if isinstance(gen_raw, dict) else {}
    feedback_raw = (raw.get("feedback") or {}) if isinstance(raw, dict) else {}
    gap_raw = (raw.get("gap") or {}) if isinstance(raw, dict) else {}

    pd = ParentDocConfig(
        enabled=bool(pd_raw.get("enabled", ParentDocConfig.enabled)),
        chunk_strategy=str(pd_raw.get("chunk_strategy", ParentDocConfig.chunk_strategy)),
        max_child_tokens=int(pd_raw.get("max_child_tokens", ParentDocConfig.max_child_tokens)),
        top_k_children=int(pd_raw.get("top_k_children", ParentDocConfig.top_k_children)),
        top_n_parents=int(pd_raw.get("top_n_parents", ParentDocConfig.top_n_parents)),
        storage=str(pd_raw.get("storage", ParentDocConfig.storage)),
    )
    td = TimeDecayConfig(
        enabled=bool(td_raw.get("enabled", TimeDecayConfig.enabled)),
        half_life_days=float(td_raw.get("half_life_days", TimeDecayConfig.half_life_days)),
        weight=float(td_raw.get("weight", TimeDecayConfig.weight)),
        date_field=str(td_raw.get("date_field", TimeDecayConfig.date_field)),
    )
    rag = RAGConfig(
        context_max_chars=int(rag_raw.get("context_max_chars", RAGConfig.context_max_chars)),
    )
    rewriter = ChatRewriterConfig(
        enabled=bool(rew_raw.get("enabled", ChatRewriterConfig.enabled)),
        model=str(rew_raw.get("model", ChatRewriterConfig.model)),
    )
    storage = StorageConfig(
        backend=str(store_raw.get("backend", StorageConfig.backend)),
        sqlite_path=str(store_raw.get("sqlite_path", StorageConfig.sqlite_path)),
        redis_url=str(store_raw.get("redis_url", StorageConfig.redis_url)),
    )
    chat = ChatConfig(
        enabled=bool(chat_raw.get("enabled", ChatConfig.enabled)),
        max_history_turns=int(
            chat_raw.get("max_history_turns", ChatConfig.max_history_turns)
        ),
        ttl_seconds=int(chat_raw.get("ttl_seconds", ChatConfig.ttl_seconds)),
        max_sessions=int(chat_raw.get("max_sessions", ChatConfig.max_sessions)),
        rewriter=rewriter,
        storage=storage,
    )
    graph = GraphConfig(
        enabled=bool(graph_raw.get("enabled", GraphConfig.enabled)),
        default_hop=int(graph_raw.get("default_hop", GraphConfig.default_hop)),
        max_neighbors_per_query=int(
            graph_raw.get(
                "max_neighbors_per_query", GraphConfig.max_neighbors_per_query
            )
        ),
        expand_on_search=bool(
            graph_raw.get("expand_on_search", GraphConfig.expand_on_search)
        ),
        knowledge_dir=str(graph_raw.get("knowledge_dir", GraphConfig.knowledge_dir)),
    )
    emb_default = EmbedderConfig()
    embedder = EmbedderConfig(
        backend=str(emb_raw.get("backend", emb_default.backend)),
        ollama=OllamaConfig(
            model=str(emb_ollama_raw.get("model", emb_default.ollama.model)),
            url=str(emb_ollama_raw.get("url", emb_default.ollama.url)),
        ),
    )
    gen_default = GenerationConfig()
    generation = GenerationConfig(
        backend=str(gen_raw.get("backend", gen_default.backend)),
        ollama=OllamaConfig(
            model=str(gen_ollama_raw.get("model", gen_default.ollama.model)),
            url=str(gen_ollama_raw.get("url", gen_default.ollama.url)),
        ),
    )
    feedback_default = FeedbackConfig()
    feedback = FeedbackConfig(
        enabled=bool(feedback_raw.get("enabled", feedback_default.enabled)),
        db_path=str(feedback_raw.get("db_path", feedback_default.db_path)),
    )
    gap_default = GapConfig()
    gap = GapConfig(
        enabled=bool(gap_raw.get("enabled", gap_default.enabled)),
        db_path=str(gap_raw.get("db_path", gap_default.db_path)),
        low_score_threshold=float(
            gap_raw.get("low_score_threshold", gap_default.low_score_threshold)
        ),
    )
    return AppConfig(
        retrieval=RetrievalConfig(parent_doc=pd, time_decay=td),
        rag=rag,
        chat=chat,
        graph=graph,
        embedder=embedder,
        generation=generation,
        feedback=feedback,
        gap=gap,
    )


# ---------------------------------------------------------------------------
# spec_042: EVAL_OVERRIDE_FLAG wiring (used by evaluation/run_abtest.py)
# ---------------------------------------------------------------------------


def _apply_override_flags(cfg: AppConfig, override: str) -> AppConfig:
    """Apply ``dotted.key=value`` overrides to ``cfg`` from EVAL_OVERRIDE_FLAG.

    Multiple overrides are ``;``-separated. Values are coerced to bool / int /
    float / str (in that order). Unknown keys are logged at WARNING level and
    silently skipped — we never raise so a stale env var can't take the API
    down.
    """
    _log = logging.getLogger(__name__)
    new_cfg = cfg
    for pair in override.split(";"):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        key, _, value = pair.partition("=")
        key = key.strip()
        value_typed = _coerce_value(value.strip())
        try:
            new_cfg = _replace_dotted(new_cfg, key, value_typed)
            _log.info("EVAL_OVERRIDE_FLAG: applied %s=%r", key, value_typed)
        except (KeyError, AttributeError, TypeError) as e:
            _log.warning("EVAL_OVERRIDE_FLAG: unknown key %r ignored (%s)", key, e)
    return new_cfg


def _coerce_value(s: str) -> bool | int | float | str:
    """Best-effort scalar coercion: bool > int > float > str."""
    low = s.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def _replace_dotted(cfg, dotted_key: str, value):
    """Return a new (frozen) dataclass with ``dotted_key`` replaced by ``value``.

    e.g. ``_replace_dotted(cfg, "retrieval.time_decay.enabled", True)`` returns
    a new ``AppConfig`` with that nested field flipped, leaving all other
    fields untouched (each enclosing dataclass is rebuilt via
    ``dataclasses.replace``).
    """
    import dataclasses

    parts = [p for p in dotted_key.split(".") if p]
    if not parts:
        raise KeyError(dotted_key)
    head, *rest = parts
    if not hasattr(cfg, head):
        raise KeyError(head)
    if not rest:
        return dataclasses.replace(cfg, **{head: value})
    inner = getattr(cfg, head)
    new_inner = _replace_dotted(inner, ".".join(rest), value)
    return dataclasses.replace(cfg, **{head: new_inner})
