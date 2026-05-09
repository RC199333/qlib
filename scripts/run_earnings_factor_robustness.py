from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_lab.earnings.seasonal_factors import SeasonalFactorRunConfig, expanded_tech_symbols
from alpha_lab.earnings.seasonal_factors import factor_definitions, run_seasonal_factor
from alpha_lab.earnings.universe import clusters_for


PEAD_LEAVE_ONE_SYMBOLS = ["CRWD", "KLAC", "MU", "INTC", "PANW", "LRCX"]
PEAD_LEAVE_ONE_CLUSTERS = ["semiconductor", "semiconductor_equipment", "enterprise_software", "cybersecurity"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run robustness variants for the earnings factor suite.")
    parser.add_argument("--provider-uri", default="~/.qlib/qlib_data/us_data_recent")
    parser.add_argument("--region", default="us")
    parser.add_argument("--start", default="2020-01-02")
    parser.add_argument("--end", default="2026-05-07")
    parser.add_argument("--output-dir", default=".tmp/factor_runs")
    parser.add_argument("--tracking-uri", default="")
    parser.add_argument("--alpha-vantage-cache-dir", default="data/alpha_lab/earnings/raw/alpha_vantage")
    return parser.parse_args()


def sanitized_command(argv: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in argv)


def _run(args: argparse.Namespace, factor_name: str, symbols: list[str]) -> Path:
    defn = factor_definitions()["PEAD_v1_quality_drift_60d"]
    config = SeasonalFactorRunConfig(
        factor_name=factor_name,
        factor_family=defn.family,
        version=defn.version,
        provider_uri=args.provider_uri,
        region=args.region,
        start=args.start,
        end=args.end,
        symbols=symbols,
        alpha_vantage_cache_dir=args.alpha_vantage_cache_dir,
        output_dir=args.output_dir,
        tracking_uri=args.tracking_uri or None,
        experiment_name="alpha_lab_earnings_robustness",
        max_active_positions=defn.max_active_positions,
        max_weight=defn.max_weight,
        hold_days=defn.default_hold_days,
        command=sanitized_command(sys.argv),
    )
    return run_seasonal_factor(config, defn)


def main() -> None:
    args = parse_args()
    base_symbols = expanded_tech_symbols()
    cluster_map = clusters_for(base_symbols)
    run_dirs = []

    for symbol in PEAD_LEAVE_ONE_SYMBOLS:
        symbols = [item for item in base_symbols if item != symbol]
        run_dirs.append(_run(args, f"PEAD_v1_quality_drift_60d_no_{symbol.lower()}", symbols))

    for cluster in PEAD_LEAVE_ONE_CLUSTERS:
        symbols = [item for item in base_symbols if cluster_map.get(item) != cluster]
        run_dirs.append(_run(args, f"PEAD_v1_quality_drift_60d_no_{cluster}", symbols))

    print("Completed robustness runs:")
    for run_dir in run_dirs:
        print(run_dir)


if __name__ == "__main__":
    main()
