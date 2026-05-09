"""Build a recent US Qlib dataset from Yahoo Finance.

This creates a separate Qlib provider directory instead of mutating the legacy
ready-made US dataset. The default universe is practical for agent-driven US
research: SP500 + NASDAQ100 + core liquid ETFs + major benchmarks.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from yahooquery import Ticker


CORE_ETFS = [
    "SPY",
    "QQQ",
    "IWM",
    "DIA",
    "VTI",
    "VOO",
    "IVV",
    "RSP",
    "XLK",
    "XLF",
    "XLE",
    "XLV",
    "XLY",
    "XLP",
    "XLI",
    "XLB",
    "XLU",
    "XLRE",
    "XLC",
    "TLT",
    "IEF",
    "SHY",
    "HYG",
    "LQD",
    "GLD",
    "SLV",
    "USO",
    "UUP",
    "EEM",
    "EFA",
    "VNQ",
]

BENCHMARKS = ["^GSPC", "^NDX", "^DJI"]


def normalize_us_symbol(symbol: str) -> str:
    return str(symbol).strip().upper().replace(".", "-")


def default_home(path: str) -> Path:
    return Path(path).expanduser().resolve()


def read_instrument_symbols(instrument_file: Path) -> list[str]:
    if not instrument_file.exists():
        return []
    df = pd.read_csv(instrument_file, sep="\t", header=None, names=["symbol", "start", "end"])
    return sorted(set(df["symbol"].dropna().astype(str).map(normalize_us_symbol)))


def read_symbol_list(symbols_file: Path) -> list[str]:
    symbols = []
    for line in symbols_file.read_text(encoding="utf-8").splitlines():
        symbol = line.strip()
        if symbol and not symbol.startswith("#"):
            symbols.append(normalize_us_symbol(symbol))
    return sorted(set(symbols))


def read_html_tables(url: str) -> list[pd.DataFrame]:
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, headers=headers, timeout=60)
    resp.raise_for_status()
    return pd.read_html(StringIO(resp.text))


def fetch_current_sp500() -> list[str]:
    tables = read_html_tables("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
    for table in tables:
        if "Symbol" in table.columns:
            return sorted(set(table["Symbol"].dropna().map(normalize_us_symbol)))
    raise RuntimeError("Could not find current SP500 table")


def fetch_current_nasdaq100() -> list[str]:
    tables = read_html_tables("https://en.wikipedia.org/wiki/Nasdaq-100")
    for table in tables:
        for column in ["Ticker", "Symbol"]:
            if column in table.columns and len(table) >= 90:
                return sorted(set(table[column].dropna().map(normalize_us_symbol)))
    raise RuntimeError("Could not find current NASDAQ100 table")


def normalize_downloaded_frame(symbol: str, hist: pd.DataFrame) -> pd.DataFrame:
    df = hist.copy()
    if df.empty:
        return df

    if isinstance(df.index, pd.MultiIndex):
        df = df.reset_index()
    else:
        df = df.reset_index()

    if "symbol" not in df.columns:
        df["symbol"] = symbol

    if "date" not in df.columns:
        if "index" in df.columns:
            df = df.rename(columns={"index": "date"})
        else:
            raise ValueError(f"{symbol}: no date column returned by Yahoo")

    df = df[df["symbol"].astype(str).str.upper() == symbol.upper()].copy()
    if df.empty:
        return df

    for col in ["open", "high", "low", "close", "volume", "adjclose"]:
        if col not in df.columns:
            df[col] = pd.NA

    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None).dt.normalize()
    df = df.sort_values("date").drop_duplicates("date")

    numeric_cols = ["open", "high", "low", "close", "volume", "adjclose"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["date", "close"])
    df = df[df["close"] > 0]
    if df.empty:
        return df

    adj_ratio = (df["adjclose"] / df["close"]).replace([np.inf, -np.inf], pd.NA)
    adj_ratio = adj_ratio.fillna(1.0)

    out = pd.DataFrame(
        {
            "date": df["date"],
            "symbol": symbol.upper(),
            "open": df["open"] * adj_ratio,
            "high": df["high"] * adj_ratio,
            "low": df["low"] * adj_ratio,
            "close": df["adjclose"].fillna(df["close"]),
            "volume": df["volume"],
            "factor": adj_ratio,
        }
    )
    out["change"] = out["close"].pct_change()
    out = out.dropna(subset=["open", "high", "low", "close"])
    return out


def download_symbols(symbols: list[str], start: str, end: str, raw_dir: Path, chunk_size: int) -> tuple[list[str], list[str]]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    ok: list[str] = []
    failed: list[str] = []

    for chunk_start in range(0, len(symbols), chunk_size):
        chunk = symbols[chunk_start : chunk_start + chunk_size]
        print(f"Downloading {chunk_start + 1}-{chunk_start + len(chunk)} / {len(symbols)}")
        try:
            hist = Ticker(chunk, asynchronous=False).history(start=start, end=end, interval="1d")
        except Exception as exc:  # noqa: BLE001
            print(f"Chunk failed: {chunk[:3]}... {exc}", file=sys.stderr)
            failed.extend(chunk)
            continue

        if isinstance(hist, dict):
            print(f"Chunk returned error dict: {hist}", file=sys.stderr)
            failed.extend(chunk)
            continue

        for symbol in chunk:
            try:
                one = normalize_downloaded_frame(symbol, hist)
                if one.empty:
                    failed.append(symbol)
                    continue
                one.to_csv(raw_dir / f"{symbol}.csv", index=False)
                ok.append(symbol)
            except Exception as exc:  # noqa: BLE001
                print(f"{symbol} failed: {exc}", file=sys.stderr)
                failed.append(symbol)

    return sorted(set(ok)), sorted(set(failed))


def write_universe(path: Path, symbols: list[str], ranges: dict[str, tuple[str, str]]) -> None:
    lines = []
    for symbol in sorted(set(symbols)):
        if symbol in ranges:
            start, end = ranges[symbol]
            lines.append(f"{symbol}\t{start}\t{end}")
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def collect_ranges(raw_dir: Path) -> dict[str, tuple[str, str]]:
    ranges: dict[str, tuple[str, str]] = {}
    for csv_path in raw_dir.glob("*.csv"):
        df = pd.read_csv(csv_path, usecols=["date", "symbol"])
        if df.empty:
            continue
        symbol = str(df["symbol"].iloc[0]).upper()
        dates = pd.to_datetime(df["date"])
        ranges[symbol] = (dates.min().strftime("%Y-%m-%d"), dates.max().strftime("%Y-%m-%d"))
    return ranges


def dump_to_qlib(repo_root: Path, raw_dir: Path, qlib_dir: Path, max_workers: int) -> None:
    cmd = [
        sys.executable,
        str(repo_root / "scripts" / "dump_bin.py"),
        "dump_all",
        "--data_path",
        str(raw_dir),
        "--qlib_dir",
        str(qlib_dir),
        "--freq",
        "day",
        "--max_workers",
        str(max_workers),
        "--exclude_fields",
        "date,symbol",
        "--file_suffix",
        ".csv",
    ]
    subprocess.run(cmd, cwd=repo_root, check=True)
    day_calendar = qlib_dir / "calendars" / "day.txt"
    day_future_calendar = qlib_dir / "calendars" / "day_future.txt"
    if day_calendar.exists() and not day_future_calendar.exists():
        shutil.copyfile(day_calendar, day_future_calendar)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-qlib-dir", default="~/.qlib/qlib_data/us_data")
    parser.add_argument("--target-qlib-dir", default="~/.qlib/qlib_data/us_data_recent")
    parser.add_argument("--raw-dir", default="~/.qlib/stock_data/source/us_recent")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default=(pd.Timestamp.today().normalize() + pd.Timedelta(days=1)).strftime("%Y-%m-%d"))
    parser.add_argument("--chunk-size", type=int, default=40)
    parser.add_argument("--max-workers", type=int, default=1)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--symbol-source", choices=["current", "legacy"], default="current")
    parser.add_argument("--symbols-file", default=None, help="Optional newline-delimited symbols to download.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    source_qlib_dir = default_home(args.source_qlib_dir)
    target_qlib_dir = default_home(args.target_qlib_dir)
    raw_dir = default_home(args.raw_dir)

    if args.symbol_source == "current":
        try:
            sp500 = fetch_current_sp500()
        except Exception as exc:  # noqa: BLE001
            print(f"Current SP500 fetch failed, falling back to legacy instruments: {exc}", file=sys.stderr)
            sp500 = read_instrument_symbols(source_qlib_dir / "instruments" / "sp500.txt")
        try:
            nasdaq100 = fetch_current_nasdaq100()
        except Exception as exc:  # noqa: BLE001
            print(f"Current NASDAQ100 fetch failed, falling back to legacy instruments: {exc}", file=sys.stderr)
            nasdaq100 = read_instrument_symbols(source_qlib_dir / "instruments" / "nasdaq100.txt")
    else:
        sp500 = read_instrument_symbols(source_qlib_dir / "instruments" / "sp500.txt")
        nasdaq100 = read_instrument_symbols(source_qlib_dir / "instruments" / "nasdaq100.txt")

    if args.symbols_file is not None:
        symbols = read_symbol_list(default_home(args.symbols_file))
    else:
        symbols = sorted(set(sp500 + nasdaq100 + CORE_ETFS + BENCHMARKS))
    if args.limit is not None:
        symbols = symbols[: args.limit]

    print(f"Universe size: {len(symbols)}")
    print(f"Date range: {args.start} -> {args.end} (end exclusive)")
    ok, failed = download_symbols(symbols, args.start, args.end, raw_dir, args.chunk_size)
    print(f"Downloaded OK: {len(ok)}")
    print(f"Failed: {len(failed)}")
    failed_path = raw_dir / "_failed_symbols.txt"
    if failed:
        failed_path.write_text("\n".join(failed) + "\n", encoding="utf-8")
    elif failed_path.exists():
        failed_path.unlink()

    if not ok:
        raise RuntimeError("No symbols were downloaded successfully")

    dump_to_qlib(repo_root, raw_dir, target_qlib_dir, args.max_workers)

    ranges = collect_ranges(raw_dir)
    inst_dir = target_qlib_dir / "instruments"
    inst_dir.mkdir(parents=True, exist_ok=True)
    write_universe(inst_dir / "sp500.txt", sp500, ranges)
    write_universe(inst_dir / "nasdaq100.txt", nasdaq100, ranges)
    write_universe(inst_dir / "etf_core.txt", CORE_ETFS, ranges)
    write_universe(inst_dir / "benchmarks.txt", BENCHMARKS, ranges)

    print(f"Recent US Qlib data is ready at {target_qlib_dir}")
    print(f"Raw CSV cache is at {raw_dir}")


if __name__ == "__main__":
    main()
