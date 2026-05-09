from __future__ import annotations

import argparse
import os
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_lab.earnings.seasonal_factors import SeasonalFactorRunConfig, expanded_tech_symbols, factor_definitions
from alpha_lab.earnings.seasonal_factors import run_seasonal_factor


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Alpha Lab earnings-season factor variants.")
    parser.add_argument("--factor", default="all", help="Factor name or 'all'.")
    parser.add_argument("--provider-uri", default="~/.qlib/qlib_data/us_data_recent")
    parser.add_argument("--region", default="us")
    parser.add_argument("--start", default="2020-01-02")
    parser.add_argument("--end", default="2026-05-07")
    parser.add_argument("--symbols", default="")
    parser.add_argument("--events-path", default="")
    parser.add_argument("--api-key", default=os.getenv("ALPHAVANTAGE_API_KEY", ""))
    parser.add_argument("--alpha-vantage-cache-dir", default="data/alpha_lab/earnings/raw/alpha_vantage")
    parser.add_argument(
        "--fundamentals-path",
        default="data/alpha_lab/fundamentals/processed/sec_companyfacts_quarterly.csv",
    )
    parser.add_argument("--output-dir", default=".tmp/factor_runs")
    parser.add_argument("--tracking-uri", default=".tmp/mlruns_alpha_lab")
    parser.add_argument("--experiment-name", default="alpha_lab_earnings_seasonal")
    parser.add_argument("--request-delay-seconds", type=float, default=0.0)
    parser.add_argument("--force-download", action="store_true")
    parser.add_argument("--one-way-cost-bps", type=float, default=10.0)
    parser.add_argument("--hold-days", type=int, default=0, help="Override the factor default holding horizon.")
    parser.add_argument("--factor-name-suffix", default="", help="Append a suffix to the factor_name for parameter sweeps.")
    parser.add_argument("--min-avg-dollar-volume-20", type=float, default=20_000_000.0)
    parser.add_argument("--max-volatility-20", type=float, default=0.10)
    parser.add_argument("--max-runup-5", type=float, default=0.12)
    parser.add_argument("--min-history-events", type=int, default=20)
    parser.add_argument("--fundamental-quality-min-rank", type=float, default=0.20)
    parser.add_argument("--fundamental-quality-min-components", type=int, default=2)
    return parser.parse_args()


def sanitized_command(argv: list[str]) -> str:
    out = []
    skip_next = False
    for arg in argv:
        if skip_next:
            skip_next = False
            continue
        if arg == "--api-key":
            out.extend([arg, "<redacted>"])
            skip_next = True
            continue
        if arg.startswith("--api-key="):
            out.append("--api-key=<redacted>")
            continue
        out.append(arg)
    return " ".join(shlex.quote(part) for part in out)


def _symbols(value: str) -> list[str]:
    if not value:
        return expanded_tech_symbols()
    return [symbol.strip().upper() for symbol in value.split(",") if symbol.strip()]


def main() -> None:
    args = parse_args()
    definitions = factor_definitions()
    if args.factor == "all":
        selected = list(definitions.values())
    else:
        if args.factor not in definitions:
            valid = ", ".join(sorted(definitions))
            raise SystemExit(f"Unknown factor {args.factor}. Valid factors: {valid}")
        selected = [definitions[args.factor]]

    run_dirs = []
    for defn in selected:
        hold_days = args.hold_days if args.hold_days > 0 else defn.default_hold_days
        factor_name = f"{defn.name}{args.factor_name_suffix}" if args.factor_name_suffix else defn.name
        config = SeasonalFactorRunConfig(
            factor_name=factor_name,
            factor_family=defn.family,
            version=defn.version,
            provider_uri=args.provider_uri,
            region=args.region,
            start=args.start,
            end=args.end,
            symbols=_symbols(args.symbols),
            events_path=args.events_path or None,
            api_key=args.api_key or None,
            alpha_vantage_cache_dir=args.alpha_vantage_cache_dir,
            fundamentals_path=args.fundamentals_path or None,
            output_dir=args.output_dir,
            tracking_uri=args.tracking_uri or None,
            experiment_name=args.experiment_name,
            request_delay_seconds=args.request_delay_seconds,
            force_download=args.force_download,
            max_active_positions=defn.max_active_positions,
            max_weight=defn.max_weight,
            one_way_cost_bps=args.one_way_cost_bps,
            hold_days=hold_days,
            min_avg_dollar_volume_20=args.min_avg_dollar_volume_20,
            max_volatility_20=args.max_volatility_20,
            max_runup_5=args.max_runup_5,
            min_history_events=args.min_history_events,
            fundamental_quality_min_rank=args.fundamental_quality_min_rank,
            fundamental_quality_min_components=args.fundamental_quality_min_components,
            command=sanitized_command(sys.argv),
        )
        run_dir = run_seasonal_factor(config, defn)
        run_dirs.append(run_dir)
        print(f"{defn.name}: {run_dir}")

    print("Completed runs:")
    for run_dir in run_dirs:
        print(run_dir)


if __name__ == "__main__":
    main()
