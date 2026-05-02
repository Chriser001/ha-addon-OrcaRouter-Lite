"""LlamaIndex LLM wrapper for OrcaRouter Lite.

Install:
    pip install llama-index-llms-openai-like

Usage:
    from llamaindex_orcarouter import OrcaRouter

    llm = OrcaRouter(model="auto", api_key="sk-orca-...")
    print(llm.complete("Hello!"))
"""

from __future__ import annotations

from typing import Any

try:
    from llama_index.llms.openai_like import OpenAILike
except ImportError as exc:
    raise ImportError(
        "llama-index-llms-openai-like is required: "
        "`pip install llama-index-llms-openai-like`"
    ) from exc


class OrcaRouter(OpenAILike):
    """`OpenAILike` configured for a local OrcaRouter Lite by default."""

    def __init__(
        self,
        *,
        model: str = "auto",
        api_key: str,
        api_base: str = "http://localhost:8000/v1",
        is_chat_model: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            model=model,
            api_key=api_key,
            api_base=api_base,
            is_chat_model=is_chat_model,
            **kwargs,
        )
