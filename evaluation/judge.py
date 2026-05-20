"""Gemini 1.5 Flash adapter for ragas LLM judge."""

from __future__ import annotations

import os

from langchain_core.language_models import BaseChatModel


def get_judge_llm() -> BaseChatModel:
    """Return ragas-compatible Gemini Flash LLM."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=0.0,
        google_api_key=api_key,
    )


def get_judge_embeddings():
    """Embeddings for ragas semantic similarity metrics (context_precision / context_recall)."""
    from langchain_google_genai import GoogleGenerativeAIEmbeddings

    return GoogleGenerativeAIEmbeddings(
        model="models/text-embedding-004",
        google_api_key=os.environ["GEMINI_API_KEY"],
    )
