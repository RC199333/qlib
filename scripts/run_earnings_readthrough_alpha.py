from __future__ import annotations

import argparse
import os
import sys
import shlex
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_lab.earnings.runner import EarningsReadthroughRunConfig, run_earnings_readthrough
from alpha_lab.earnings.universe import default_tech_symbols


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Alpha Lab earnings read-through strategy.")
    parser.add_argument("--factor-name", default="ERT_v0_4_target_quality_readthrough_band")
    parser.add_argument("--provider-uri", default="~/.qlib/qlib_data/us_data_recent")
    parser.add_argument("--region", default="us")
    parser.add_argument("--start", default="2020-01-02")
    parser.add_argument("--end", default="2026-05-07")
    parser.add_argument("--symbols", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--events-path", default="")
    parser.add_argument("--api-key", default=os.getenv("ALPHAVANTAGE_API_KEY", ""))
    parser.add_argument("--alpha-vantage-cache-dir", default="data/alpha_lab/earnings/raw/alpha_vantage")
    parser.add_argument("--output-dir", default=".tmp/factor_runs")
    parser.add_argument("--tracking-uri", default=".tmp/mlruns_alpha_lab")
    parser.add_argument("--experiment-name", default="alpha_lab_ERT_v0_4")
    parser.add_argument("--request-delay-seconds", type=float, default=0.0)
    parser.add_argument("--force-download", action="store_true")
    parser.add_argument("--lookback-days", type=int, default=45)
    parser.add_argument("--peer-half-life-days", type=int, default=20)
    parser.add_argument("--min-peer-events", type=int, default=3)
    parser.add_argument("--score-threshold", type=float, default=None)
    parser.add_argument("--selection-quantile", type=float, default=None)
    parser.add_argument("--selection-min-quantile", type=float, default=0.0)
    parser.add_argument("--selection-max-quantile", type=float, default=0.80)
    parser.add_argument("--min-history-events", type=int, default=20)
    parser.add_argument("--max-runup-5", type=float, default=0.05)
    parser.add_argument("--max-volatility-20", type=float, default=0.08)
    parser.add_argument("--min-avg-dollar-volume-20", type=float, default=20_000_000.0)
    parser.add_argument("--min-peer-excess-hit-rate", type=float, default=0.50)
    parser.add_argument("--min-target-prior-events", type=int, default=4)
    parser.add_argument("--min-target-prior-excess-median", type=float, default=0.0)
    parser.add_argument("--max-active-positions", type=int, default=10)
    parser.add_argument("--max-weight", type=float, default=0.10)
    parser.add_argument("--one-way-cost-bps", type=float, default=10.0)
    return parser.parse_args()


def sanitized_command(argv: list[str]) -> str:
    out = []
    skip_next = False
    for i, arg in enumerate(argv):
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


def main() -> None:
    args = parse_args()
    if args.symbols:
        symbols = [symbol.strip().upper() for symbol in args.symbols.split(",") if symbol.strip()]
    else:
        symbols = default_tech_symbols()
    if args.limit > 0:
        symbols = symbols[: args.limit]
    config = EarningsReadthroughRunConfig(
        factor_name=args.factor_name,
        provider_uri=args.provider_uri,
        region=args.region,
        start=args.start,
        end=args.end,
        symbols=symbols,
        events_path=args.events_path or None,
        api_key=args.api_key or None,
        alpha_vantage_cache_dir=args.alpha_vantage_cache_dir,
        output_dir=args.output_dir,
        tracking_uri=args.tracking_uri or None,
        experiment_name=args.experiment_name,
        request_delay_seconds=args.request_delay_seconds,
        force_download=args.force_download,
        lookback_days=args.lookback_days,
        peer_half_life_days=args.peer_half_life_days,
        min_peer_events=args.min_peer_events,
        score_threshold=args.score_threshold,
        selection_quantile=args.selection_quantile,
        selection_min_quantile=args.selection_min_quantile,
        selection_max_quantile=args.selection_max_quantile,
        min_history_events=args.min_history_events,
        max_runup_5=args.max_runup_5,
        max_volatility_20=args.max_volatility_20,
        min_avg_dollar_volume_20=args.min_avg_dollar_volume_20,
        min_peer_excess_hit_rate=args.min_peer_excess_hit_rate,
        min_target_prior_events=args.min_target_prior_events,
        min_target_prior_excess_median=args.min_target_prior_excess_median,
        max_active_positions=args.max_active_positions,
        max_weight=args.max_weight,
        one_way_cost_bps=args.one_way_cost_bps,
        command=sanitized_command(sys.argv),
    )
    run_dir = run_earnings_readthrough(config)
    print(f"Earnings read-through run complete: {run_dir}")


if __name__ == "__main__":
    main()
