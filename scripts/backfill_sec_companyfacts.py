from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_lab.data_sources.sec_companyfacts import SECCompanyFactsClient, load_sec_quarterly_fundamentals
from alpha_lab.earnings.seasonal_factors import expanded_tech_symbols


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill SEC companyfacts quarterly fundamentals.")
    parser.add_argument("--symbols", default="", help="Comma-separated symbols. Defaults to expanded tech universe.")
    parser.add_argument("--limit", type=int, default=0, help="Maximum symbols to request. 0 means all.")
    parser.add_argument("--cache-dir", default="data/alpha_lab/fundamentals/raw/sec_companyfacts")
    parser.add_argument(
        "--output",
        default="data/alpha_lab/fundamentals/processed/sec_companyfacts_quarterly.csv",
    )
    parser.add_argument("--user-agent", default="", help="SEC User-Agent. Defaults to SEC_USER_AGENT env var.")
    parser.add_argument("--sleep", type=float, default=0.12, help="Seconds between SEC requests.")
    parser.add_argument("--force", action="store_true", help="Re-download cached SEC companyfacts.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned symbols without downloading.")
    return parser.parse_args()


def _symbols(value: str) -> list[str]:
    if value:
        return sorted({symbol.strip().upper() for symbol in value.split(",") if symbol.strip()})
    return expanded_tech_symbols()


def _cached_cik_count(cache_dir: Path) -> int:
    companyfacts_dir = cache_dir / "companyfacts"
    if not companyfacts_dir.exists():
        return 0
    return len(list(companyfacts_dir.glob("CIK*.json")))


def main() -> None:
    args = parse_args()
    cache_dir = Path(args.cache_dir)
    symbols = _symbols(args.symbols)
    if args.limit and args.limit > 0:
        symbols = symbols[: args.limit]
    print(f"requested_symbols={len(symbols)} cached_companyfacts={_cached_cik_count(cache_dir)}")
    if symbols:
        print("planned_symbols=" + ",".join(symbols))
    if args.dry_run:
        return

    client = SECCompanyFactsClient(
        cache_dir=cache_dir,
        user_agent=args.user_agent or None,
    )
    fundamentals, failed = load_sec_quarterly_fundamentals(
        client=client,
        symbols=symbols,
        delay_seconds=args.sleep,
        force=args.force,
    )
    if fundamentals.empty:
        raise SystemExit("No SEC quarterly fundamentals were loaded.")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fundamentals.to_csv(output, index=False)
    print(f"rows={len(fundamentals)} symbols={fundamentals['symbol'].nunique()} output={output}")
    if failed:
        print("failed_symbols=" + ",".join(failed))


if __name__ == "__main__":
    main()
