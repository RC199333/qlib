"""Markdown reporting for earnings read-through runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pandas as pd


def _fmt(value: Any, pct: bool = False) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    if pct:
        return f"{float(value):.2%}"
    return f"{float(value):.4f}"


def build_report(
    run_name: str,
    summary: Dict[str, Dict[str, float]],
    signals: pd.DataFrame,
    event_returns: pd.DataFrame,
    assumptions: Dict[str, Any],
    metrics_by_year: pd.DataFrame | None = None,
    data_diagnostics: Dict[str, Any] | None = None,
    experiment_spec: Dict[str, Any] | None = None,
    plots: list[str] | None = None,
    metrics_summary: Dict[str, Any] | None = None,
) -> str:
    selected = signals[signals["selected"]].copy() if not signals.empty else pd.DataFrame()
    hit_rate = selected["event_return"].gt(0).mean() if "event_return" in selected else pd.NA
    avg_event = selected["event_return"].mean() if "event_return" in selected else pd.NA
    top = event_returns.sort_values("event_return_after_cost", ascending=False).head(5)
    bottom = event_returns.sort_values("event_return_after_cost", ascending=True).head(5)

    lines = [
        f"# {run_name}",
        "",
        "## Summary",
        "",
        f"- selected_events: {len(selected)}",
        f"- eligible_events: {int(signals['eligible'].sum()) if 'eligible' in signals else 0}",
        f"- tradable_signals: {int(signals['tradable_signal'].sum()) if 'tradable_signal' in signals else 0}",
        f"- hit_rate: {_fmt(hit_rate, pct=True)}",
        f"- average_event_return: {_fmt(avg_event, pct=True)}",
        "",
        "## Portfolio Metrics",
        "",
    ]
    for name, metrics in summary.items():
        lines.append(f"### {name}")
        lines.append("")
        if name == "selected_event":
            lines.append(f"- selected_events: {_fmt(metrics.get('selected_events'))}")
            lines.append(f"- hit_rate: {_fmt(metrics.get('hit_rate'), pct=True)}")
            lines.append(f"- average_event_return_after_cost: {_fmt(metrics.get('average_event_return_after_cost'), pct=True)}")
            for key, value in metrics.items():
                if key.startswith("average_excess_vs_"):
                    lines.append(f"- {key}: {_fmt(value, pct=True)}")
            lines.append("")
            continue
        lines.append(f"- cumulative_return: {_fmt(metrics.get('cumulative_return'), pct=True)}")
        lines.append(f"- annualized_return: {_fmt(metrics.get('annualized_return'), pct=True)}")
        lines.append(f"- sharpe_or_ir: {_fmt(metrics.get('sharpe', metrics.get('information_ratio')))}")
        lines.append(f"- max_drawdown: {_fmt(metrics.get('max_drawdown'), pct=True)}")
        lines.append("")

    if metrics_by_year is not None and not metrics_by_year.empty:
        lines.extend(["## Yearly Metrics", "", "```text", metrics_by_year.to_string(index=False), "```", ""])
    if plots:
        lines.extend(["## Plots", ""])
        for plot in plots:
            lines.append(f"- `{plot}`")
        lines.append("")
    if metrics_summary and metrics_summary.get("signal_diagnostics"):
        lines.extend(
            [
                "## Signal Diagnostics",
                "",
                "```json",
                json.dumps(metrics_summary["signal_diagnostics"], indent=2, sort_keys=True, default=str),
                "```",
                "",
            ]
        )
    top_text = f"```text\n{top.to_string(index=False)}\n```" if not top.empty else "No selected events."
    bottom_text = f"```text\n{bottom.to_string(index=False)}\n```" if not bottom.empty else "No selected events."
    lines.extend(["## Top Events", "", top_text, ""])
    lines.extend(["## Bottom Events", "", bottom_text, ""])
    if experiment_spec:
        lines.extend(
            ["## Experiment Spec", "", "```json", json.dumps(experiment_spec, indent=2, sort_keys=True, default=str), "```", ""]
        )
    if data_diagnostics:
        lines.extend(
            ["## Data Diagnostics", "", "```json", json.dumps(data_diagnostics, indent=2, sort_keys=True, default=str), "```", ""]
        )
    lines.extend(["## Assumptions", "", "```json", json.dumps(assumptions, indent=2, sort_keys=True, default=str), "```", ""])
    return "\n".join(lines)


def write_report(path: str | Path, *args, **kwargs) -> Path:
    path = Path(path)
    path.write_text(build_report(*args, **kwargs), encoding="utf-8")
    return path
