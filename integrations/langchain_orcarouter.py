"""LangChain LLM wrapper for OrcaRouter Lite.

Lite speaks the OpenAI Chat Completions protocol, so we subclass `ChatOpenAI`
with sensible defaults pointing at the local server. Use `model="auto"` to let
OrcaRouter pick the cheapest capable model for each call.

Install:
    pip install langchain-openai

Usage:
    from langchain_orcarouter import OrcaRouter

    llm = OrcaRouter(model="auto", api_key="sk-orca-...")
    print(llm.invoke("Hello in haiku form"))
"""

from __future__ import annotations

from typing import Any

try:
    from langchain_openai import ChatOpenAI
except ImportError as exc:
    raise ImportError(
        "langchain-openai is required: `pip install langchain-openai`"
    ) from exc


class OrcaRouter(ChatOpenAI):
    """Drop-in `ChatOpenAI` that talks to a local OrcaRouter Lite by default.

    Override `base_url` to point at a remote Lite or hosted orcarouter.ai.
    """

    def __init__(
        self,
        *,
        model: str = "auto",
        api_key: str,
        base_url: str = "http://localhost:8000/v1",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            model=model,
            api_key=api_key,
            base_url=base_url,
            **kwargs,
        )
