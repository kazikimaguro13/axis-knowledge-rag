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


@dataclass(frozen=True)
class RetrievalConfig:
    parent_doc: ParentDocConfig = field(default_factory=ParentDocConfig)


@dataclass(frozen=True)
class RAGConfig:
    context_max_chars: int = 8000


# ---------------------------------------------------------------------------
# spec_032: conversational RAG settings
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChatRewriterConfig:
    enabled: bool = True
    model: str = "gemini-1.5-flash"


@dataclass(frozen=True)
class ChatConfig:
    """Settings for the conversational ``/api/chat`` path."""

    enabled: bool = True
    max_history_turns: int = 6   # 6 turn = 12 messages kept in store
    ttl_seconds: int = 86400     # 24h since last access → evicted
    max_sessions: int = 100      # LRU cap
    rewriter: ChatRewriterConfig = field(default_factory=ChatRewriterConfig)


@dataclass(frozen=True)
class AppConfig:
    """Aggregated runtime config (axes + retrieval + rag + chat)."""

    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    rag: RAGConfig = field(default_factory=RAGConfig)
    chat: ChatConfig = field(default_factory=ChatConfig)


def load_app_config(path: Path | None = None) -> AppConfig:
    """Load full ``config.yml`` into the typed ``AppConfig`` (with defaults).

    Missing keys / missing file → all defaults. Unknown keys are ignored
    so older config files keep working.
    """
    import yaml

    config_path = path or Path("./config.yml")
    if not config_path.exists():
        return AppConfig()
    try:
        with open(config_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except OSError:
        return AppConfig()

    retr_raw = (raw.get("retrieval") or {}) if isinstance(raw, dict) else {}
    pd_raw = (retr_raw.get("parent_doc") or {}) if isinstance(retr_raw, dict) else {}
    rag_raw = (raw.get("rag") or {}) if isinstance(raw, dict) else {}
    chat_raw = (raw.get("chat") or {}) if isinstance(raw, dict) else {}
    rew_raw = (chat_raw.get("rewriter") or {}) if isinstance(chat_raw, dict) else {}

    pd = ParentDocConfig(
        enabled=bool(pd_raw.get("enabled", ParentDocConfig.enabled)),
        chunk_strategy=str(pd_raw.get("chunk_strategy", ParentDocConfig.chunk_strategy)),
        max_child_tokens=int(pd_raw.get("max_child_tokens", ParentDocConfig.max_child_tokens)),
        top_k_children=int(pd_raw.get("top_k_children", ParentDocConfig.top_k_children)),
        top_n_parents=int(pd_raw.get("top_n_parents", ParentDocConfig.top_n_parents)),
    )
    rag = RAGConfig(
        context_max_chars=int(rag_raw.get("context_max_chars", RAGConfig.context_max_chars)),
    )
    rewriter = ChatRewriterConfig(
        enabled=bool(rew_raw.get("enabled", ChatRewriterConfig.enabled)),
        model=str(rew_raw.get("model", ChatRewriterConfig.model)),
    )
    chat = ChatConfig(
        enabled=bool(chat_raw.get("enabled", ChatConfig.enabled)),
        max_history_turns=int(
            chat_raw.get("max_history_turns", ChatConfig.max_history_turns)
        ),
        ttl_seconds=int(chat_raw.get("ttl_seconds", ChatConfig.ttl_seconds)),
        max_sessions=int(chat_raw.get("max_sessions", ChatConfig.max_sessions)),
        rewriter=rewriter,
    )
    return AppConfig(retrieval=RetrievalConfig(parent_doc=pd), rag=rag, chat=chat)
