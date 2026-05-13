"""Pydantic schemas for the ingester (memo → YAML frontmatter Markdown).

`IngestResult` is what we ask Claude to produce. The schema doubles as a
runtime guard against hallucinated fields (`refs` must look like doc IDs, etc).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IngestResult(BaseModel):
    """The structured response we ask Claude to produce."""

    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(..., description="Unique doc id, e.g. 'doc_011'", pattern=r"^doc_\d{3,}$")
    title: str = Field(..., min_length=3, max_length=200)
    axes: dict[str, str | int] = Field(..., description="Filled axis values")
    tags: list[str] = Field(default_factory=list, max_length=10)
    refs: list[str] = Field(default_factory=list)
    body: str = Field(..., min_length=20)

    @field_validator("refs")
    @classmethod
    def _refs_format(cls, v: list[str]) -> list[str]:
        for r in v:
            if not r.startswith("doc_"):
                raise ValueError(f"Invalid ref id: {r}")
        return v


class IngestOptions(BaseModel):
    """Options for one ingest call."""

    model_config = ConfigDict(str_strip_whitespace=True)

    knowledge_dir: str = Field(
        default="./examples/knowledge",
        description="Existing knowledge dir to derive next id and validate refs against.",
    )
    suggested_category: str | None = Field(
        default=None,
        description="Hint to bias Claude's category choice (e.g. '議事録').",
    )
    max_tokens: int = Field(default=1500, ge=512, le=4096)
    retry_count: int = Field(
        default=2,
        description="Number of retries when Claude returns invalid JSON (0 disables retry).",
        ge=0,
        le=5,
    )
