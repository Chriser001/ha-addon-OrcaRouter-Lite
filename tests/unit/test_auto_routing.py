"""model="auto" — pick the cheapest model that meets capability requirements.

The contract:
  1. Inspect the request to figure out required capabilities (tools, vision,
     json_mode) from `tools` / `tool_choice` / `response_format` / message
     image content.
  2. From the catalog, filter to models that advertise every required
     capability.
  3. From the deployable subset (configured providers + hosted upstream),
     pick the cheapest by blended (input + output) per-token cost.
  4. Return that model id, which the chat handler then sends to the router.

This is the differentiated feature that LiteLLM's Router does not provide.
"""

from __future__ import annotations

# ── capability detection ────────────────────────────────────────────────

def test_required_capabilities_empty_for_plain_chat():
    from app.auto_routing import required_capabilities

    body = {"messages": [{"role": "user", "content": "hi"}]}
    assert required_capabilities(body) == set()


def test_required_capabilities_picks_up_tools():
    from app.auto_routing import required_capabilities

    body = {
        "messages": [{"role": "user", "content": "hi"}],
        "tools": [{"type": "function", "function": {"name": "foo"}}],
    }
    assert "tools" in required_capabilities(body)


def test_required_capabilities_skips_tools_when_choice_is_none():
    """`tool_choice=none` is an explicit opt-out — don't force a tool-capable model."""
    from app.auto_routing import required_capabilities

    body = {
        "messages": [{"role": "user", "content": "hi"}],
        "tools": [{"type": "function", "function": {"name": "foo"}}],
        "tool_choice": "none",
    }
    assert "tools" not in required_capabilities(body)


def test_required_capabilities_picks_up_json_mode():
    from app.auto_routing import required_capabilities

    body = {
        "messages": [{"role": "user", "content": "hi"}],
        "response_format": {"type": "json_object"},
    }
    assert "json_mode" in required_capabilities(body)


def test_required_capabilities_picks_up_vision_from_image_url_content():
    from app.auto_routing import required_capabilities

    body = {
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": "what's this?"},
                {"type": "image_url", "image_url": {"url": "data:..."}},
            ],
        }],
    }
    assert "vision" in required_capabilities(body)


# ── selection ───────────────────────────────────────────────────────────

def test_choose_model_picks_cheapest_meeting_no_requirements():
    from app.auto_routing import choose_auto_model
    from packages.litellm_adapter.catalog import CatalogModel

    candidates = [
        CatalogModel("expensive", "openai", "openai/", True, True, True, 1e-5, 3e-5),
        CatalogModel("cheap", "openai", "openai/", True, False, False, 1e-7, 4e-7),
        CatalogModel("medium", "openai", "openai/", True, True, True, 1e-6, 3e-6),
    ]
    deployable = {"cheap", "medium", "expensive"}
    chosen = choose_auto_model(needs=set(), deployable=deployable, candidates=candidates)
    assert chosen == "cheap"


def test_choose_model_excludes_non_deployable():
    """A model that's in the catalog but has no provider key wired up is skipped."""
    from app.auto_routing import choose_auto_model
    from packages.litellm_adapter.catalog import CatalogModel

    candidates = [
        CatalogModel("free-but-not-keyed", "openai", "openai/", True, False, False, 0.0, 0.0),
        CatalogModel("cheap-and-keyed", "anthropic", "anthropic/", True, False, False, 1e-7, 4e-7),
    ]
    deployable = {"cheap-and-keyed"}  # only this provider has a key
    chosen = choose_auto_model(needs=set(), deployable=deployable, candidates=candidates)
    assert chosen == "cheap-and-keyed"


def test_choose_model_filters_by_capability():
    from app.auto_routing import choose_auto_model
    from packages.litellm_adapter.catalog import CatalogModel

    candidates = [
        # Cheapest but no vision support — must be skipped when vision required.
        CatalogModel("cheap-no-vision", "groq", "groq/", True, False, False, 1e-8, 1e-8),
        # More expensive but supports vision — should win.
        CatalogModel("vision-capable", "openai", "openai/", True, True, True, 1e-6, 3e-6),
    ]
    deployable = {"cheap-no-vision", "vision-capable"}
    chosen = choose_auto_model(
        needs={"vision"}, deployable=deployable, candidates=candidates
    )
    assert chosen == "vision-capable"


def test_choose_model_returns_none_when_no_candidate_satisfies():
    from app.auto_routing import choose_auto_model
    from packages.litellm_adapter.catalog import CatalogModel

    candidates = [
        CatalogModel("text-only", "groq", "groq/", True, False, False, 1e-8, 1e-8),
    ]
    chosen = choose_auto_model(
        needs={"vision"}, deployable={"text-only"}, candidates=candidates
    )
    assert chosen is None


def test_choose_model_uses_blended_input_plus_output_cost():
    """Realistic scoring weights output 70% (typical I/O ratio for chat)."""
    from app.auto_routing import choose_auto_model
    from packages.litellm_adapter.catalog import CatalogModel

    candidates = [
        # High input, tiny output → low blended cost (mostly output)
        CatalogModel("a", "openai", "openai/", True, False, False, 1e-5, 1e-7),
        # Low input, high output → high blended cost
        CatalogModel("b", "openai", "openai/", True, False, False, 1e-7, 1e-5),
    ]
    chosen = choose_auto_model(
        needs=set(), deployable={"a", "b"}, candidates=candidates
    )
    assert chosen == "a"


# ── strategy-aware selection ────────────────────────────────────────────

def test_choose_model_quality_strategy_picks_most_expensive():
    """`quality` is the inverse of `cheapest` — biggest as a proxy for best."""
    from app.auto_routing import choose_auto_model
    from packages.litellm_adapter.catalog import CatalogModel

    candidates = [
        CatalogModel("cheap", "openai", "openai/", True, False, False, 1e-7, 4e-7),
        CatalogModel("medium", "openai", "openai/", True, False, False, 1e-6, 3e-6),
        CatalogModel("expensive", "openai", "openai/", True, False, False, 1e-5, 3e-5),
    ]
    chosen = choose_auto_model(
        needs=set(),
        deployable={"cheap", "medium", "expensive"},
        candidates=candidates,
        strategy="quality",
    )
    assert chosen == "expensive"


def test_choose_model_cheapest_strategy_matches_default():
    from app.auto_routing import choose_auto_model
    from packages.litellm_adapter.catalog import CatalogModel

    candidates = [
        CatalogModel("cheap", "openai", "openai/", True, False, False, 1e-7, 4e-7),
        CatalogModel("expensive", "openai", "openai/", True, False, False, 1e-5, 3e-5),
    ]
    chosen = choose_auto_model(
        needs=set(),
        deployable={"cheap", "expensive"},
        candidates=candidates,
        strategy="cheapest",
    )
    assert chosen == "cheap"


def test_choose_model_preferred_models_narrows_eligible_set():
    """When `preferred_models` is set and any are eligible, restrict to them."""
    from app.auto_routing import choose_auto_model
    from packages.litellm_adapter.catalog import CatalogModel

    candidates = [
        CatalogModel("cheap-not-preferred", "openai", "openai/", True, False, False, 1e-8, 1e-8),
        CatalogModel("preferred-mid", "openai", "openai/", True, False, False, 1e-6, 3e-6),
        CatalogModel("preferred-big", "openai", "openai/", True, False, False, 1e-5, 3e-5),
    ]
    chosen = choose_auto_model(
        needs=set(),
        deployable={"cheap-not-preferred", "preferred-mid", "preferred-big"},
        candidates=candidates,
        strategy="cheapest",
        preferred_models=["preferred-mid", "preferred-big"],
    )
    assert chosen == "preferred-mid"  # cheapest within the preferred set


def test_choose_model_preferred_models_falls_back_when_none_eligible():
    """If preferred_models has no eligible entries, ignore the filter."""
    from app.auto_routing import choose_auto_model
    from packages.litellm_adapter.catalog import CatalogModel

    candidates = [
        CatalogModel("cheap", "openai", "openai/", True, False, False, 1e-7, 4e-7),
    ]
    chosen = choose_auto_model(
        needs=set(),
        deployable={"cheap"},
        candidates=candidates,
        preferred_models=["does-not-exist", "neither-does-this"],
    )
    assert chosen == "cheap"


# ── litellm strategy mapping ────────────────────────────────────────────

def test_litellm_routing_strategy_maps_known_values():
    from app.auto_routing import litellm_routing_strategy

    assert litellm_routing_strategy("cheapest") == "cost-based-routing"
    assert litellm_routing_strategy("fastest") == "latency-based-routing"
    # `balanced` and `quality` use litellm's default (no override)
    assert litellm_routing_strategy("balanced") is None
    assert litellm_routing_strategy("quality") is None


def test_litellm_routing_strategy_returns_none_for_unknown_or_empty():
    from app.auto_routing import litellm_routing_strategy

    assert litellm_routing_strategy(None) is None
    assert litellm_routing_strategy("") is None
    assert litellm_routing_strategy("not-a-real-strategy") is None
