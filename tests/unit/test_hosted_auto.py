"""Unit tests for `_hosted_auto_savings` — the hosted-auto comparison
that powers the second row of the savings KPI in the dashboard.

These tests bypass the analytics fixture and call the function directly
with a synthetic catalog so we can pin behavior on edge cases (token-mix
asymmetry, zero-priced models) without depending on whatever litellm
ships in `model_cost`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class _StubModel:
    """Subset of CatalogModel that `_hosted_auto_savings` consumes."""
    id: str
    supports_tools: bool = False
    supports_vision: bool = False
    supports_json_mode: bool = False
    input_cost_per_token: float = 0.0
    output_cost_per_token: float = 0.0


def _build(catalog: list) -> tuple[list, dict]:
    return catalog, {m.id: m for m in catalog}


def test_hosted_auto_picks_cheapest_for_each_row_actual_tokens():
    """Codex P2: _hosted_auto_savings was using a fixed 30/70 blended cost
    weight to pick a single fallback model per `model_resolved`. For
    input-heavy or output-heavy requests, that's not the cheapest for
    that request. The endpoint claims "cheapest per request" — and we
    have per-row tokens — so cost should be minimized using each row's
    actual input/output mix.

    Setup: two candidates whose ranking flips depending on token mix.
      A: cheap output, pricey input  (great for output-heavy traffic)
      B: cheap input,  pricey output (great for input-heavy traffic)

    Two request rows: one input-heavy, one output-heavy.
    The cheapest possible total spans BOTH models (A for the
    output-heavy row, B for the input-heavy row). A 30/70 blended
    pick of one model can never beat that combined min.
    """
    from app.routes.analytics import _hosted_auto_savings

    A = _StubModel("A", input_cost_per_token=10e-6, output_cost_per_token=1e-6)
    B = _StubModel("B", input_cost_per_token=1e-6,  output_cost_per_token=10e-6)
    Resolved = _StubModel("R", input_cost_per_token=100e-6, output_cost_per_token=100e-6)
    catalog, by_id = _build([A, B, Resolved])

    # Costs in microcents:
    #   row1 (10000 in / 100 out): A → 10000*10 + 100*1   = 100100
    #                              B → 10000*1  + 100*10  =  11000  ← cheapest
    #   row2 (100 in / 10000 out): A → 100*10   + 10000*1 =  11000  ← cheapest
    #                              B → 100*1    + 10000*10= 100100
    # Per-row optimum total: 11000 + 11000 = 22000
    # Blended-30/70 picks: A blended = 0.3*10+0.7*1 = 3.7
    #                     B blended = 0.3*1+0.7*10 = 7.3 → A wins blended.
    # Single-model A total: 100100 + 11000 = 111100. Per-row beats by 5×.
    rows = [
        # (input_tokens, output_tokens, cost_microcents, model_resolved)
        (10000, 100,   500_000, "R"),  # actual cost arbitrary, > both candidates
        (100,   10000, 500_000, "R"),
    ]

    result = _hosted_auto_savings(rows, catalog, by_id)
    assert result["comparable_request_count"] == 2
    # The hosted-auto cost must equal the per-row optimum (22000),
    # not the single-model blended pick (111100). With a tolerance of
    # 1 microcent for int rounding.
    assert result["actual_microcents"] <= 22_001, (
        f"hosted_auto picked {result['actual_microcents']} microcents — "
        "expected per-row minimum of 22000. A 30/70 blended single-pick "
        "would give 111100; that's the bug."
    )


def test_hosted_auto_falls_back_to_zero_for_non_catalog_resolved():
    """Pre-existing behavior: rows whose model_resolved isn't in the
    catalog are dropped from the comparison."""
    from app.routes.analytics import _hosted_auto_savings

    A = _StubModel("A", input_cost_per_token=1e-6, output_cost_per_token=1e-6)
    catalog, by_id = _build([A])

    rows = [(100, 100, 999_000, "not-in-catalog")]
    result = _hosted_auto_savings(rows, catalog, by_id)
    assert result["comparable_request_count"] == 0
    assert result["actual_microcents"] == 0
    assert result["saved_microcents"] == 0


def test_hosted_auto_filters_candidates_by_capability():
    """A row resolved to a vision-capable model can only be compared
    against vision-capable candidates — never downgrade capabilities."""
    from app.routes.analytics import _hosted_auto_savings

    cheap_no_vision = _StubModel(
        "cheap", supports_vision=False,
        input_cost_per_token=1e-9, output_cost_per_token=1e-9,
    )
    pricey_with_vision = _StubModel(
        "vis", supports_vision=True,
        input_cost_per_token=1e-6, output_cost_per_token=1e-6,
    )
    resolved_with_vision = _StubModel(
        "R", supports_vision=True,
        input_cost_per_token=100e-6, output_cost_per_token=100e-6,
    )
    catalog, by_id = _build([cheap_no_vision, pricey_with_vision, resolved_with_vision])

    rows = [(1000, 1000, 200_000, "R")]
    result = _hosted_auto_savings(rows, catalog, by_id)
    # Must pick `vis` (1e-6 each), not `cheap` (1e-9). Cost = 1000+1000 = 2000 microcents.
    assert result["actual_microcents"] == 2000
