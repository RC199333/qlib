"""Alpha Vantage adapter for earnings research data."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any, Dict, Iterable, Optional
from urllib.parse import urlencode
from urllib.request import urlopen

import pandas as pd


class AlphaVantageError(RuntimeError):
    """Raised when Alpha Vantage data cannot be loaded."""


def _safe_symbol(symbol: str) -> str:
    return symbol.replace("/", "_").replace("\\", "_").replace("^", "INDEX_").upper()


def _to_number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.replace({"None": pd.NA, "": pd.NA}), errors="coerce")


@dataclass
class AlphaVantageClient:
    api_key: Optional[str] = None
    cache_dir: Path = Path("data/alpha_lab/earnings/raw/alpha_vantage")
    base_url: str = "https://www.alphavantage.co/query"
    timeout: int = 60

    def __post_init__(self) -> None:
        self.cache_dir = Path(self.cache_dir)

    @classmethod
    def from_env(cls, cache_dir: Path | str = Path("data/alpha_lab/earnings/raw/alpha_vantage")):
        return cls(api_key=os.getenv("ALPHAVANTAGE_API_KEY"), cache_dir=Path(cache_dir))

    def _require_api_key(self) -> str:
        if not self.api_key:
            raise AlphaVantageError(
                "ALPHAVANTAGE_API_KEY is not set. Provide --api-key, set the env var, "
                "or run with --events-path for an offline event CSV."
            )
        return self.api_key

    def _request_text(self, params: Dict[str, Any]) -> str:
        query = urlencode({k: v for k, v in params.items() if v is not None})
        with urlopen(f"{self.base_url}?{query}", timeout=self.timeout) as resp:  # noqa: S310
            return resp.read().decode("utf-8")

    def get_json(self, function: str, symbol: str, force: bool = False) -> Dict[str, Any]:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = self.cache_dir / function.lower() / f"{_safe_symbol(symbol)}.json"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        if cache_path.exists() and not force:
            return json.loads(cache_path.read_text(encoding="utf-8"))

        text = self._request_text(
            {
                "function": function,
                "symbol": symbol,
                "apikey": self._require_api_key(),
            }
        )
        data = json.loads(text)
        if "Error Message" in data or "Information" in data or "Note" in data:
            raise AlphaVantageError(f"Alpha Vantage {function} failed for {symbol}: {data}")
        cache_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        return data

    def get_csv(
        self,
        function: str,
        symbol: Optional[str] = None,
        horizon: Optional[str] = None,
        force: bool = False,
    ) -> pd.DataFrame:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        key = _safe_symbol(symbol or "ALL")
        suffix = f"_{horizon}" if horizon else ""
        cache_path = self.cache_dir / function.lower() / f"{key}{suffix}.csv"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        if cache_path.exists() and not force:
            return pd.read_csv(cache_path)

        text = self._request_text(
            {
                "function": function,
                "symbol": symbol,
                "horizon": horizon,
                "apikey": self._require_api_key(),
            }
        )
        if text.lstrip().startswith("{"):
            data = json.loads(text)
            raise AlphaVantageError(f"Alpha Vantage {function} failed for {symbol or 'ALL'}: {data}")
        cache_path.write_text(text, encoding="utf-8")
        return pd.read_csv(StringIO(text))

    def earnings(self, symbol: str, force: bool = False) -> pd.DataFrame:
        return normalize_earnings_payload(symbol, self.get_json("EARNINGS", symbol, force=force))

    def earnings_calendar(self, symbol: Optional[str] = None, horizon: str = "12month") -> pd.DataFrame:
        return normalize_earnings_calendar(self.get_csv("EARNINGS_CALENDAR", symbol=symbol, horizon=horizon))


def normalize_earnings_payload(symbol: str, payload: Dict[str, Any]) -> pd.DataFrame:
    rows = payload.get("quarterlyEarnings", [])
    if not rows:
        return pd.DataFrame(
            columns=[
                "symbol",
                "reported_date",
                "fiscal_date_ending",
                "reported_eps",
                "estimated_eps",
                "surprise",
                "surprise_percentage",
            ]
        )

    df = pd.DataFrame(rows)
    out = pd.DataFrame(
        {
            "symbol": symbol.upper(),
            "reported_date": pd.to_datetime(df.get("reportedDate"), errors="coerce"),
            "fiscal_date_ending": pd.to_datetime(df.get("fiscalDateEnding"), errors="coerce"),
            "reported_eps": _to_number(df.get("reportedEPS", pd.Series(dtype=object))),
            "estimated_eps": _to_number(df.get("estimatedEPS", pd.Series(dtype=object))),
            "surprise": _to_number(df.get("surprise", pd.Series(dtype=object))),
            "surprise_percentage": _to_number(df.get("surprisePercentage", pd.Series(dtype=object))),
        }
    )
    out = out.dropna(subset=["reported_date"])
    out["reported_date"] = out["reported_date"].dt.normalize()
    return out.sort_values(["reported_date", "symbol"]).reset_index(drop=True)


def normalize_earnings_calendar(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["symbol", "name", "reported_date", "fiscal_date_ending", "estimated_eps"])
    out = pd.DataFrame(
        {
            "symbol": df.get("symbol", pd.Series(dtype=object)).astype(str).str.upper(),
            "name": df.get("name", pd.Series(dtype=object)),
            "reported_date": pd.to_datetime(df.get("reportDate"), errors="coerce"),
            "fiscal_date_ending": pd.to_datetime(df.get("fiscalDateEnding"), errors="coerce"),
            "estimated_eps": _to_number(df.get("estimate", pd.Series(dtype=object))),
        }
    )
    out = out.dropna(subset=["symbol", "reported_date"])
    out["reported_date"] = out["reported_date"].dt.normalize()
    return out.sort_values(["reported_date", "symbol"]).reset_index(drop=True)


def load_earnings_history(
    client: AlphaVantageClient,
    symbols: Iterable[str],
    delay_seconds: float = 0.0,
    force: bool = False,
) -> pd.DataFrame:
    symbol_list = list(symbols)
    frames = []
    for idx, symbol in enumerate(symbol_list):
        try:
            frames.append(client.earnings(symbol, force=force))
        except AlphaVantageError as exc:
            if "ALPHAVANTAGE_API_KEY" in str(exc):
                raise
            print(f"{symbol}: {exc}")
        if delay_seconds > 0 and idx < len(symbol_list) - 1:
            time.sleep(delay_seconds)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).sort_values(["reported_date", "symbol"]).reset_index(drop=True)
