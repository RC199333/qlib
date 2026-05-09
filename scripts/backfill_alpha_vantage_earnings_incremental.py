from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_lab.data_sources.alpha_vantage import AlphaVantageClient, AlphaVantageError
from alpha_lab.earnings.seasonal_factors import expanded_tech_symbols


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Incrementally backfill Alpha Vantage earnings cache.")
    parser.add_argument("--api-key", default=os.getenv("ALPHAVANTAGE_API_KEY", ""))
    parser.add_argument("--cache-dir", default="data/alpha_lab/earnings/raw/alpha_vantage")
    parser.add_argument("--symbols", default="", help="Comma-separated symbols. Defaults to expanded tech universe.")
    parser.add_argument("--limit", type=int, default=20, help="Maximum symbols to request this run.")
    parser.add_argument("--sleep", type=float, default=13.0, help="Seconds between requests.")
    parser.add_argument("--force", action="store_true", help="Re-download even if cache exists.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned symbols without downloading.")
    return parser.parse_args()


def _symbols(value: str) -> list[str]:
    if value:
        return sorted({symbol.strip().upper() for symbol in value.split(",") if symbol.strip()})
    return expanded_tech_symbols()


def _cached_symbols(cache_dir: Path) -> set[str]:
    earnings_dir = cache_dir / "earnings"
    if not earnings_dir.exists():
        return set()
    return {path.stem.upper() for path in earnings_dir.glob("*.json")}


def main() -> None:
    args = parse_args()
    cache_dir = Path(args.cache_dir)
    symbols = _symbols(args.symbols)
    cached = _cached_symbols(cache_dir)
    todo = symbols if args.force else [symbol for symbol in symbols if symbol not in cached]
    todo = todo[: max(args.limit, 0)]

    print(f"requested_symbols={len(symbols)} cached={len(cached)} planned={len(todo)}")
    if todo:
        print("planned_symbols=" + ",".join(todo))
    if args.dry_run or not todo:
        return
    if not args.api_key:
        raise SystemExit("Missing API key. Pass --api-key or set ALPHAVANTAGE_API_KEY.")

    client = AlphaVantageClient(api_key=args.api_key, cache_dir=cache_dir)
    downloaded: list[str] = []
    failed: list[str] = []
    for idx, symbol in enumerate(todo):
        try:
            client.earnings(symbol, force=args.force)
            downloaded.append(symbol)
            print(f"downloaded {symbol}")
        except AlphaVantageError as exc:
            failed.append(symbol)
            print(f"failed {symbol}: {exc}")
            if "standard API rate limit" in str(exc) or "rate limit" in str(exc).lower():
                break
        if args.sleep > 0 and idx < len(todo) - 1:
            time.sleep(args.sleep)

    print(f"downloaded={len(downloaded)} failed={len(failed)}")
    if failed:
        print("failed_symbols=" + ",".join(failed))


if __name__ == "__main__":
    main()
