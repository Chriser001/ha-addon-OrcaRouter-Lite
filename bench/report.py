"""Aggregation + markdown rendering for the public benchmark."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone


def summarize(results: list[dict]) -> list[dict]:
    """Group raw per-request rows into per-model summaries."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        groups[r["model"]].append(r)

    out: list[dict] = []
    for model, rows in groups.items():
        successes = [r for r in rows if r.get("ok")]
        success_rate = len(successes) / len(rows) if rows else 0.0
        total_cost = sum(r["cost_usd"] for r in successes)
        avg_latency = (
            sum(r["latency_ms"] for r in successes) / len(successes)
            if successes else 0
        )
        out.append({
            "model": model,
            "request_count": len(rows),
            "total_cost_usd": total_cost,
            "avg_latency_ms": int(avg_latency),
            "success_rate": success_rate,
        })
    return out


def render_markdown(summary: list[dict], *, total_prompts: int) -> str:
    """Public-facing benchmark report. Sortable by cost ascending."""
    if not summary:
        return "# OrcaRouter benchmark\n\n_no benchmark results yet._\n"

    sorted_summary = sorted(summary, key=lambda r: r["total_cost_usd"])
    cheapest = sorted_summary[0]
    most_expensive = sorted_summary[-1]
    savings_pct = 0
    if most_expensive["total_cost_usd"] > 0:
        savings_pct = round(
            100 * (most_expensive["total_cost_usd"] - cheapest["total_cost_usd"])
            / most_expensive["total_cost_usd"]
        )

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# OrcaRouter benchmark",
        "",
        f"_{total_prompts} prompts × {len(summary)} models · last run {now}_",
        "",
        f"**TL;DR**: routing the cheapest capable model saved **~{savings_pct}%** "
        f"vs. the most expensive (`{most_expensive['model']}` → `{cheapest['model']}`)",
        "",
        "| Model | Requests | Total cost | Avg latency | Success |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in sorted_summary:
        lines.append(
            f"| `{row['model']}` "
            f"| {row['request_count']} "
            f"| ${row['total_cost_usd']:.2f} "
            f"| {row['avg_latency_ms']} ms "
            f"| {row['success_rate'] * 100:.0f}% |"
        )
    lines.extend([
        "",
        "_Run nightly via GitHub Actions; see `.github/workflows/benchmark.yml`._",
        "_Reproduce: `python bench/run.py --prompts bench/prompts.jsonl`_",
        "",
    ])
    return "\n".join(lines)
