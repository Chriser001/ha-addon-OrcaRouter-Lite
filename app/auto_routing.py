"""`model="auto"` — pick the cheapest catalog model that meets the request's
capability requirements AND has a deployable provider configured.

Two pure functions:
  - `required_capabilities(body)`  → set of {"tools", "vision", "json_mode"}
  - `choose_auto_model(needs, deployable, candidates)` → model_id | None

The chat handler resolves `model="auto"` by:
  1. computing needs = required_capabilities(request_body)
  2. computing deployable = {dep.model_name for dep in active_deployments}
  3. calling choose_auto_model(needs, deployable, CATALOG)
  4. swapping the resolved id into the request before calling the router

Adapted from `apps/api/routes/chat.py:_required_capabilities` /
`_score_model_for_auto` in the SaaS edition.
"""

from __future__ import annotations

from collections.abc import Iterable

from packages.litellm_adapter.catalog import CatalogModel

_CAP_FIELD = {
    "tools": "supports_tools",
    "vision": "supports_vision",
    "json_mode": "supports_json_mode",
}


# Blended weights — chat output dominates cost in practice. Same heuristic
# as `apps/api/router_cache.py:_provider_order_key`.
_INPUT_WEIGHT = 0.3
_OUTPUT_WEIGHT = 0.7


def _has_vision_content(messages: list[dict]) -> bool:
    for m in messages or []:
        content = m.get("content")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") in (
                    "image_url", "image", "input_image",
                ):
                    return True
    return False


def required_capabilities(body: dict) -> set[str]:
    """Return the set of capabilities the request needs."""
    needs: set[str] = set()

    has_tools_payload = bool(body.get("tools"))
    tool_choice = body.get("tool_choice")
    tool_choice_explicit_none = (
        isinstance(tool_choice, str) and tool_choice == "none"
    )

    if has_tools_payload and not tool_choice_explicit_none:
        needs.add("tools")
    if isinstance(tool_choice, dict):
        needs.add("tools")
    elif isinstance(tool_choice, str) and tool_choice not in ("", "none"):
        needs.add("tools")

    rf = body.get("response_format")
    if isinstance(rf, dict) and rf.get("type") in ("json_object", "json_schema"):
        needs.add("json_mode")

    if _has_vision_content(body.get("messages") or []):
        needs.add("vision")

    return needs


def _model_meets(model: CatalogModel, needs: Iterable[str]) -> bool:
    return all(getattr(model, _CAP_FIELD[n], False) for n in needs if n in _CAP_FIELD)


def _blended_cost(model: CatalogModel) -> float:
    return (
        _INPUT_WEIGHT * model.input_cost_per_token
        + _OUTPUT_WEIGHT * model.output_cost_per_token
    )


def choose_auto_model(
    *,
    needs: set[str],
    deployable: set[str],
    candidates: Iterable[CatalogModel],
) -> str | None:
    """Return the cheapest deployable model matching all `needs`, or None.

    Excludes models with zero blended cost — those are unpriced entries in
    litellm's catalogue, not actually free, and routing to them would skew
    the savings calculation.
    """
    eligible = [
        m for m in candidates
        if m.id in deployable
        and _model_meets(m, needs)
        and _blended_cost(m) > 0
    ]
    if not eligible:
        return None
    eligible.sort(key=lambda m: (_blended_cost(m), m.id))
    return eligible[0].id
