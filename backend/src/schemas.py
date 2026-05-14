"""Pydantic schemas for the FastAPI layer."""

from datetime import datetime

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    version: str
    embedder_mode: str
    rag_mode: str


class AxisDef(BaseModel):
    name: str
    type: str
    values: list[str] | None = None
    required: bool = False


class AxesResponse(BaseModel):
    axes: list[AxisDef]


class SearchRequest(BaseModel):
    query: str | None = Field(default=None, description="Natural-language query")
    filters: dict[str, str | int] = Field(default_factory=dict)
    top_k: int = Field(default=5, ge=1, le=50)


class SearchResultPayload(BaseModel):
    id: str
    title: str
    score: float
    axes: dict[str, str | int]
    body_snippet: str
    path: str
    refs: list[str] = Field(default_factory=list)


class SearchResponse(BaseModel):
    results: list[SearchResultPayload]


class AnswerRequest(BaseModel):
    question: str
    filters: dict[str, str | int] = Field(default_factory=dict)
    top_k: int = Field(default=5, ge=1, le=20)
    max_tokens: int = Field(default=1024, ge=128, le=4096)


class AnswerResponse(BaseModel):
    text: str
    cited_ids: list[str]
    sources: list[SearchResultPayload]
    is_dummy: bool
    model: str | None


# ---------------------------------------------------------------------------
# spec_032: conversational RAG
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    session_id: str | None = Field(
        default=None,
        description="Existing session id. Omit to start a fresh conversation.",
    )
    filters: dict[str, str | int] = Field(default_factory=dict)
    top_k: int = Field(default=5, ge=1, le=20)
    max_tokens: int = Field(default=1024, ge=128, le=4096)


class ChatResponseModel(BaseModel):
    session_id: str
    question: str
    rewritten_question: str | None
    answer: str
    cited_ids: list[str]
    sources: list[SearchResultPayload]
    is_dummy: bool
    model: str | None


class ChatMessagePayload(BaseModel):
    role: str
    content: str
    sources: list[dict] = Field(default_factory=list)
    timestamp: datetime


class ChatHistoryResponse(BaseModel):
    session_id: str
    messages: list[ChatMessagePayload]
