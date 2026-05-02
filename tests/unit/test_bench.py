"""Public benchmark — pure-Python aggregation logic.

The benchmark runs N prompts through M models, records (cost, latency,
output_tokens), and produces a markdown report. Tests cover the
aggregation/report logic in isolation; the real `run.py` driver hits the
network and is exercised in CI on a schedule, not in unit tests.
"""

from __future__ import annotations


def test_summarize_groups_results_by_model():
    from bench.report import summarize

    results = [
        {"model": "gpt-4o-mini", "cost_usd": 0.001, "latency_ms": 100, "output_tokens": 50, "ok": True},
        {"model": "gpt-4o-mini", "cost_usd": 0.002, "latency_ms": 150, "output_tokens": 80, "ok": True},
        {"model": "claude-3-5-haiku-latest", "cost_usd": 0.0005, "latency_ms": 200, "output_tokens": 60, "ok": True},
    ]
    s = summarize(results)
    assert {row["model"] for row in s} == {"gpt-4o-mini", "claude-3-5-haiku-latest"}
    gpt = next(r for r in s if r["model"] == "gpt-4o-mini")
    assert gpt["request_count"] == 2
    assert gpt["total_cost_usd"] == 0.003
    assert gpt["avg_latency_ms"] == 125
    assert gpt["success_rate"] == 1.0


def test_summarize_excludes_failures_from_cost_total():
    from bench.report import summarize

    results = [
        {"model": "m1", "cost_usd": 0.01, "latency_ms": 100, "output_tokens": 50, "ok": True},
        {"model": "m1", "cost_usd": 0.0, "latency_ms": 30000, "output_tokens": 0, "ok": False},
    ]
    s = summarize(results)
    row = s[0]
    assert row["request_count"] == 2
    assert row["success_rate"] == 0.5
    assert row["total_cost_usd"] == 0.01  # failure cost excluded


def test_render_markdown_includes_all_models_sorted_by_cost():
    from bench.report import render_markdown

    summary = [
        {"model": "expensive", "request_count": 10, "total_cost_usd": 1.50,
         "avg_latency_ms": 500, "success_rate": 1.0},
        {"model": "cheap", "request_count": 10, "total_cost_usd": 0.05,
         "avg_latency_ms": 200, "success_rate": 1.0},
    ]
    md = render_markdown(summary, total_prompts=10)
    assert "| Model |" in md  # table header
    # Cheapest sorts first
    cheap_idx = md.index("cheap")
    expensive_idx = md.index("expensive")
    assert cheap_idx < expensive_idx
    assert "$0.05" in md
    assert "$1.50" in md
    assert "10 prompts" in md


def test_render_markdown_handles_empty_summary():
    from bench.report import render_markdown
    md = render_markdown([], total_prompts=0)
    assert "no benchmark results" in md.lower()
