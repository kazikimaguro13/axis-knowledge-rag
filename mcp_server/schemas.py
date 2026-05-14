"""Pydantic input models for the MCP server tools."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ResponseFormat(StrEnum):
    MARKDOWN = "markdown"
    JSON = "json"


class _BaseInput(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )


class SearchInput(_BaseInput):
    query: str | None = Field(
        default=None,
        description=(
            "Natural-language search query (e.g., 'RAG architecture design'). "
            "If omitted, axis filters alone determine the result set."
        ),
        max_length=500,
    )
    filters: dict[str, str | int] = Field(
        default_factory=dict,
        description=(
            "Axis filters as a flat dict, e.g. {'category': '技術記事', 'level': '中級'}. "
            "Keys must match axes defined in config.yml."
        ),
    )
    top_k: int = Field(
        default=5,
        description="Maximum number of results to return.",
        ge=1,
        le=50,
    )
    bm25_weight: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description=(
            "Weight of BM25 score in the hybrid fusion with vector cosine "
            "(0.0 = vector only, 1.0 = BM25 only). Has no effect when the "
            "server has no BM25 index wired up."
        ),
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' for humans, 'json' for programmatic use.",
    )

    @field_validator("query")
    @classmethod
    def _empty_to_none(cls, v: str | None) -> str | None:
        if v is not None and v.strip() == "":
            return None
        return v


class AnswerInput(_BaseInput):
    question: str = Field(
        ...,
        description="The question to ask. Used as both retrieval query and LLM prompt.",
        min_length=1,
        max_length=1000,
    )
    filters: dict[str, str | int] = Field(default_factory=dict, description="Axis filters (same shape as search).")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of documents to include as context.")
    max_tokens: int = Field(default=1024, ge=128, le=4096, description="Max tokens for the Claude response.")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class ListAxesInput(_BaseInput):
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class CheckIntegrityInput(_BaseInput):
    knowledge_dir: str = Field(
        default="./examples/knowledge",
        description="Path to the knowledge directory (Markdown files).",
    )
    strict: bool = Field(
        default=False,
        description="If true, return a non-zero exit-style summary when broken refs are found.",
    )
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class ListDocumentsInput(_BaseInput):
    filters: dict[str, str | int] = Field(default_factory=dict, description="Axis filters.")
    limit: int = Field(default=20, ge=1, le=100, description="Max results.")
    offset: int = Field(default=0, ge=0, description="Skip this many results.")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class ChatInput(_BaseInput):
    question: str = Field(
        ...,
        description="User's question (may be a follow-up that depends on prior turns).",
        min_length=1,
        max_length=1000,
    )
    session_id: str | None = Field(
        default=None,
        description=(
            "Existing session id from a previous axis_chat call. Omit to start a "
            "fresh conversation; the server will return a new session_id you can "
            "feed back into the next call to keep context."
        ),
    )
    filters: dict[str, str | int] = Field(
        default_factory=dict,
        description="Optional axis filters (same shape as axis_search).",
    )
    top_k: int = Field(default=5, ge=1, le=20)
    max_tokens: int = Field(default=1024, ge=128, le=4096)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class NeighborsInput(_BaseInput):
    doc_id: str = Field(
        ...,
        description="Document id (e.g. 'doc_001') whose graph neighbours to return.",
        min_length=1,
        max_length=128,
    )
    hop: int = Field(
        default=1,
        ge=1,
        le=3,
        description="BFS depth — 1 returns direct refs neighbours.",
    )
    max_neighbors: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Cap on the number of neighbours returned.",
    )
    direction: str = Field(
        default="both",
        description="'out' (this doc's refs), 'in' (docs that reference this), or 'both'.",
    )
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class IngestInput(_BaseInput):
    raw_text: str = Field(
        ...,
        description="Raw memo text to convert into YAML-frontmatter Markdown.",
        min_length=20,
        max_length=10000,
    )
    knowledge_dir: str = Field(
        default="./examples/knowledge",
        description="Existing knowledge dir, used to derive next id and validate refs.",
    )
    suggested_category: str | None = Field(
        default=None,
        description="Optional category hint (e.g. '議事録') to bias Claude's axis pick.",
    )
    max_tokens: int = Field(default=1500, ge=512, le=4096)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)
