#!/usr/bin/env python
"""Validate a Qlib factor research run directory.

This utility checks the artifact contract used by the qlib-factor-research
skill. It intentionally validates presence and basic schema only; it does not
claim that a backtest is economically valid.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable


COMMON_REQUIRED_FILES = [
    "manifest.json",
    "idea_card.json",
    "experiment_spec.json",
    "report.md",
    "commands.txt",
    "metrics_summary.json",
    "metrics_by_year.csv",
    "data_diagnostics.json",
]

FEATURE_SIGNAL_OPTIONS = [
    ("features.csv", "features.parquet"),
    ("signals.csv", "signals.parquet"),
]

REQUIRED_MANIFEST_KEYS = [
    "factor_name",
    "factor_family",
    "version",
    "status",
    "created_at",
    "provider_uri",
    "universe",
    "date_range",
    "benchmark",
    "execution",
    "data_sources",
    "artifacts",
    "validation",
    "commands",
]

BASE_REQUIRED_PLOTS = [
    "cumulative_return.png",
    "drawdown.png",
    "yearly_returns.png",
    "signal_distribution.png",
    "turnover_or_event_count.png",
]

EVENT_REQUIRED_FILES = [
    "events.csv",
    "selected_events.csv",
    "event_returns.csv",
    "positions.csv",
    "daily_returns.csv",
]

EVENT_REQUIRED_PLOTS = [
    "event_return_distribution.png",
    "selected_trade_timeline.png",
    "top_bottom_trades.png",
]


def _missing_files(root: Path, names: Iterable[str]) -> list[str]:
    return [name for name in names if not (root / name).is_file()]


def _missing_any_options(root: Path, option_groups: Iterable[tuple[str, ...]]) -> list[str]:
    missing = []
    for options in option_groups:
        if not any((root / option).is_file() for option in options):
            missing.append(" or ".join(options))
    return missing


def _load_manifest(root: Path) -> tuple[dict, list[str]]:
    path = root / "manifest.json"
    if not path.is_file():
        return {}, ["manifest.json missing"]
    try:
        return json.loads(path.read_text(encoding="utf-8-sig")), []
    except json.JSONDecodeError as exc:
        return {}, [f"manifest.json is invalid JSON: {exc}"]


def validate_run(root: Path, event: bool = False) -> list[str]:
    errors: list[str] = []
    if not root.exists():
        return [f"run directory does not exist: {root}"]
    if not root.is_dir():
        return [f"path is not a directory: {root}"]

    errors.extend(_missing_files(root, COMMON_REQUIRED_FILES))
    errors.extend(_missing_any_options(root, FEATURE_SIGNAL_OPTIONS))

    manifest, manifest_errors = _load_manifest(root)
    errors.extend(manifest_errors)
    if manifest:
        missing_keys = [key for key in REQUIRED_MANIFEST_KEYS if key not in manifest]
        errors.extend([f"manifest missing key: {key}" for key in missing_keys])

    plots_dir = root / "plots"
    if not plots_dir.is_dir():
        errors.append("plots directory missing")
    else:
        errors.extend([f"plots/{name}" for name in _missing_files(plots_dir, BASE_REQUIRED_PLOTS)])

    if event:
        errors.extend(_missing_files(root, EVENT_REQUIRED_FILES))
        if plots_dir.is_dir():
            errors.extend([f"plots/{name}" for name in _missing_files(plots_dir, EVENT_REQUIRED_PLOTS)])

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a Qlib factor research run directory.")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--event", action="store_true", help="Require event-strategy artifacts.")
    args = parser.parse_args()

    errors = validate_run(args.run_dir, event=args.event)
    if errors:
        print("FAIL")
        for error in errors:
            print(f"- {error}")
        return 1

    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
