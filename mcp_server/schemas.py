"""Pydantic input models for the MCP server tools."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ResponseFormat(str, Enum):
    MARKDOWN = "markdown"
    JSON = "json"


class _BaseInput(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )


class SearchInput(_BaseInput):
    query: Optional[str] = Field(
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
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' for humans, 'json' for programmatic use.",
    )

    @field_validator("query")
    @classmethod
    def _empty_to_none(cls, v: Optional[str]) -> Optional[str]:
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
