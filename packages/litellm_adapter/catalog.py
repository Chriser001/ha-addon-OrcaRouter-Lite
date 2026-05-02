"""Model catalog for orcarouter-lite — sourced from litellm.model_cost.

LiteLLM ships a community-maintained catalogue of ~2,600 models across
~100 providers (the `model_cost` dict). Lite reads it once at import time,
filters to chat-capable entries from the providers we care about, and
exposes them as `CatalogModel` records with capability flags + per-token
pricing.

Falls back to a small static seed when litellm isn't installed (tests
of unrelated modules don't need it).
"""

from __future__ import annotations

from dataclasses import dataclass

# ── Provider mapping: litellm prefix → (our provider id, litellm prefix string) ──
# Each entry maps a litellm provider key (the part before the `/` in the model
# string, or the `litellm_provider` field in model_cost) to our internal id +
# the full prefix used when constructing litellm_model strings.
_PROVIDER_BY_LITELLM_KEY: dict[str, tuple[str, str]] = {
    "openai": ("openai", "openai/"),
    "anthropic": ("anthropic", "anthropic/"),
    "gemini": ("google", "gemini/"),
    "vertex_ai-language-models": ("google", "gemini/"),
    "groq": ("groq", "groq/"),
    "together_ai": ("together", "together_ai/"),
    "fireworks_ai": ("fireworks", "fireworks_ai/"),
    "mistral": ("mistral", "mistral/"),
    "deepseek": ("deepseek", "deepseek/"),
    "cohere_chat": ("cohere", "cohere_chat/"),
    "perplexity": ("perplexity", "perplexity/"),
    "xai": ("xai", "xai/"),
}

# Models where litellm doesn't tag mode but we know they're chat-capable.
_FORCE_INCLUDE = {"o1", "o1-mini", "o3", "o3-mini"}

# Excluded non-chat modes.
_EXCLUDED_MODES = {"embedding", "image_generation", "audio_speech",
                   "audio_transcription", "rerank", "moderation"}


@dataclass(frozen=True)
class CatalogModel:
    id: str
    provider: str
    litellm_prefix: str
    supports_tools: bool = False
    supports_vision: bool = False
    supports_json_mode: bool = False
    input_cost_per_token: float = 0.0
    output_cost_per_token: float = 0.0


def _is_chat_model(meta: dict) -> bool:
    mode = meta.get("mode", "chat")
    if mode in _EXCLUDED_MODES:
        return False
    return mode in ("chat", "completion") or mode == "chat"


def _strip_prefix(litellm_id: str) -> str:
    """`anthropic/claude-3-5-sonnet-latest` → `claude-3-5-sonnet-latest`."""
    return litellm_id.split("/", 1)[1] if "/" in litellm_id else litellm_id


def _build_catalog_from_litellm() -> list[CatalogModel]:
    try:
        import litellm
    except Exception:
        return _STATIC_FALLBACK[:]

    out: list[CatalogModel] = []
    seen: set[str] = set()
    model_cost = getattr(litellm, "model_cost", {}) or {}

    for raw_id, meta in model_cost.items():
        if not isinstance(meta, dict):
            continue
        litellm_provider = meta.get("litellm_provider", "")
        mapped = _PROVIDER_BY_LITELLM_KEY.get(litellm_provider)
        if mapped is None:
            continue
        provider_id, prefix = mapped
        if not _is_chat_model(meta) and _strip_prefix(raw_id) not in _FORCE_INCLUDE:
            continue

        canonical = _strip_prefix(raw_id)
        # Some entries duplicate (e.g. "openai/gpt-4o" and "gpt-4o"); first wins.
        if canonical in seen:
            continue
        seen.add(canonical)

        out.append(
            CatalogModel(
                id=canonical,
                provider=provider_id,
                litellm_prefix=prefix,
                supports_tools=bool(
                    meta.get("supports_function_calling")
                    or meta.get("supports_tool_choice")
                ),
                supports_vision=bool(meta.get("supports_vision")),
                supports_json_mode=bool(
                    meta.get("supports_response_schema")
                    or meta.get("supports_json_schema")
                ),
                input_cost_per_token=float(meta.get("input_cost_per_token") or 0.0),
                output_cost_per_token=float(meta.get("output_cost_per_token") or 0.0),
            )
        )

    # Make sure a few flagship aliases are always present even if the litellm
    # version pins a different canonical ID. This keeps demos / examples stable
    # across litellm upgrades.
    flagship = {
        "claude-3-5-sonnet-latest": (
            "anthropic", "anthropic/", True, True, False,
            3e-6, 1.5e-5,
        ),
        "claude-3-5-haiku-latest": (
            "anthropic", "anthropic/", True, False, False,
            8e-7, 4e-6,
        ),
    }
    existing_ids = {m.id for m in out}
    for fid, (prov, prefix, tools, vision, json_mode, in_c, out_c) in flagship.items():
        if fid not in existing_ids:
            out.append(CatalogModel(
                id=fid, provider=prov, litellm_prefix=prefix,
                supports_tools=tools, supports_vision=vision,
                supports_json_mode=json_mode,
                input_cost_per_token=in_c, output_cost_per_token=out_c,
            ))

    out.sort(key=lambda m: (m.provider, m.id))
    return out


# Tiny fallback used when litellm isn't importable.
_STATIC_FALLBACK: list[CatalogModel] = [
    CatalogModel("gpt-4o", "openai", "openai/", True, True, True, 2.5e-6, 1e-5),
    CatalogModel("gpt-4o-mini", "openai", "openai/", True, True, True, 1.5e-7, 6e-7),
    CatalogModel("claude-3-5-sonnet-latest", "anthropic", "anthropic/", True, True, False, 3e-6, 1.5e-5),
    CatalogModel("claude-3-5-haiku-latest", "anthropic", "anthropic/", True, False, False, 8e-7, 4e-6),
    CatalogModel("gemini-1.5-pro", "google", "gemini/", True, True, True, 1.25e-6, 5e-6),
    CatalogModel("gemini-1.5-flash", "google", "gemini/", True, True, True, 7.5e-8, 3e-7),
]


CATALOG: list[CatalogModel] = _build_catalog_from_litellm()
CATALOG_BY_ID: dict[str, CatalogModel] = {m.id: m for m in CATALOG}
PROVIDERS_TO_MODELS: dict[str, list[CatalogModel]] = {}
for _m in CATALOG:
    PROVIDERS_TO_MODELS.setdefault(_m.provider, []).append(_m)


def all_model_ids() -> list[str]:
    return list(CATALOG_BY_ID.keys())


def models_for_provider(provider: str) -> list[CatalogModel]:
    return PROVIDERS_TO_MODELS.get(provider, [])
