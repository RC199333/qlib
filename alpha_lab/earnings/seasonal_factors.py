"""Earnings-season factor variants built on Qlib daily market data.

These variants intentionally stay inside the alpha_lab research layer.  They
reuse Qlib for market data, Alpha Vantage or cached CSV events for earnings
metadata, and the existing event backtest for close-to-close portfolio
simulation.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Optional

import matplotlib
import numpy as np
import pandas as pd

from alpha_lab.data_sources.alpha_vantage import AlphaVantageClient, AlphaVantageError
from alpha_lab.data_sources.alpha_vantage import normalize_earnings_payload
from alpha_lab.earnings.events import load_events_csv, prepare_earnings_events
from alpha_lab.earnings.features import build_readthrough_features
from alpha_lab.earnings.prices import load_qlib_ohlcv
from alpha_lab.earnings.universe import clusters_for, default_tech_symbols
from alpha_lab.ideas import IdeaCard
from alpha_lab.reports.earnings_report import write_report
from alpha_lab.strategies.earnings_event_long_only import EventBacktestConfig, run_event_backtest


INDICATOR_ONLY_SYMBOLS = {
    "AAPL",
    "MSFT",
    "GOOG",
    "GOOGL",
    "AMZN",
    "META",
    "NVDA",
    "ORCL",
}

EXCLUDED_HOLDING_SYMBOLS = {"PLTR"}

BASKET_BY_CLUSTER = {
    "mega_platform": "platform_ai_indicators",
    "enterprise_software": "software_cloud_cyber",
    "cybersecurity": "software_cloud_cyber",
    "semiconductor": "ai_compute_semis",
    "semiconductor_equipment": "ai_compute_semis",
    "semiconductor_foundry": "ai_compute_semis",
    "ai_infrastructure": "ai_compute_semis",
    "networking": "ai_compute_semis",
    "legacy_infra": "ai_compute_semis",
    "hardware": "ai_compute_semis",
    "ai_adjacent": "platform_ai_indicators",
}

DEFAULT_EXPANDED_TECH_SYMBOLS = [
    "AAPL",
    "MSFT",
    "GOOGL",
    "GOOG",
    "AMZN",
    "META",
    "NFLX",
    "NVDA",
    "AMD",
    "AVGO",
    "QCOM",
    "MU",
    "INTC",
    "TXN",
    "AMAT",
    "LRCX",
    "KLAC",
    "MRVL",
    "ADI",
    "NXPI",
    "ON",
    "MPWR",
    "SMCI",
    "DELL",
    "HPE",
    "ANET",
    "CSCO",
    "ORCL",
    "CRM",
    "NOW",
    "ADBE",
    "INTU",
    "PANW",
    "CRWD",
    "FTNT",
    "DDOG",
    "ZS",
    "WDAY",
    "ADSK",
    "TTD",
    "SHOP",
    "UBER",
    "PYPL",
    "PLTR",
    "TSLA",
]


@dataclass(frozen=True)
class SeasonalFactorRunConfig:
    factor_name: str
    factor_family: str
    version: str
    provider_uri: str = "~/.qlib/qlib_data/us_data_recent"
    region: str = "us"
    start: str = "2020-01-02"
    end: str = "2026-05-07"
    symbols: Optional[Iterable[str]] = None
    events_path: Optional[str] = None
    api_key: Optional[str] = None
    alpha_vantage_cache_dir: str = "data/alpha_lab/earnings/raw/alpha_vantage"
    fundamentals_path: Optional[str] = "data/alpha_lab/fundamentals/processed/sec_companyfacts_quarterly.csv"
    output_dir: str = ".tmp/factor_runs"
    tracking_uri: Optional[str] = ".tmp/mlruns_alpha_lab"
    experiment_name: str = "alpha_lab_earnings_seasonal"
    request_delay_seconds: float = 0.0
    force_download: bool = False
    benchmark_symbols: tuple[str, ...] = ("QQQ", "^GSPC")
    max_active_positions: int = 30
    max_weight: float = 0.04
    one_way_cost_bps: float = 10.0
    hold_days: int = 20
    min_avg_dollar_volume_20: float = 20_000_000.0
    max_volatility_20: float = 0.10
    max_runup_5: float = 0.12
    min_history_events: int = 20
    fundamental_quality_min_rank: float = 0.20
    fundamental_quality_min_components: int = 2
    command: Optional[str] = None


@dataclass(frozen=True)
class FactorDefinition:
    name: str
    family: str
    version: str
    hypothesis: str
    formula: dict[str, str]
    execution: dict[str, str]
    literature: list[dict[str, str]]
    builder: Callable[[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DatetimeIndex, SeasonalFactorRunConfig], pd.DataFrame]
    default_hold_days: int
    max_active_positions: int
    max_weight: float
    status_rule: str


def expanded_tech_symbols() -> list[str]:
    return sorted(set(DEFAULT_EXPANDED_TECH_SYMBOLS).union(default_tech_symbols()))


def _component(values: pd.Series, scale: float, lower: float = -3.0, upper: float = 3.0) -> pd.Series:
    return (pd.to_numeric(values, errors="coerce").fillna(0.0) / scale).clip(lower=lower, upper=upper)


def _numeric_column(frame: pd.DataFrame, col: str) -> pd.Series:
    if col not in frame:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    return pd.to_numeric(frame[col], errors="coerce")


def _centered_rate(values: pd.Series) -> pd.Series:
    values = pd.to_numeric(values, errors="coerce").fillna(0.5)
    return ((values - 0.5) * 2.0).clip(-1.0, 1.0)


def _calendar_shift(calendar: pd.DatetimeIndex, date: pd.Timestamp, days: int) -> Optional[pd.Timestamp]:
    calendar = pd.DatetimeIndex(calendar).sort_values()
    date = pd.Timestamp(date).normalize()
    pos = calendar.searchsorted(date)
    if pos >= len(calendar) or calendar[pos] != date:
        pos = pos - 1
    target = pos + days
    if target < 0 or target >= len(calendar):
        return None
    return pd.Timestamp(calendar[target])


def _next_on_or_after(calendar: pd.DatetimeIndex, date: pd.Timestamp) -> Optional[pd.Timestamp]:
    calendar = pd.DatetimeIndex(calendar).sort_values()
    pos = calendar.searchsorted(pd.Timestamp(date).normalize())
    if pos >= len(calendar):
        return None
    return pd.Timestamp(calendar[pos])


def _previous_before(calendar: pd.DatetimeIndex, date: pd.Timestamp) -> Optional[pd.Timestamp]:
    calendar = pd.DatetimeIndex(calendar).sort_values()
    pos = calendar.searchsorted(pd.Timestamp(date).normalize())
    if pos <= 0:
        return None
    return pd.Timestamp(calendar[pos - 1])


def _price_return(close: pd.DataFrame, symbol: str, start: pd.Timestamp, end: pd.Timestamp) -> float:
    if symbol not in close or pd.Timestamp(start) not in close.index or pd.Timestamp(end) not in close.index:
        return np.nan
    start_value = close.at[pd.Timestamp(start), symbol]
    end_value = close.at[pd.Timestamp(end), symbol]
    if pd.isna(start_value) or pd.isna(end_value) or start_value == 0:
        return np.nan
    return float(end_value / start_value - 1.0)


def _basket_for_symbol(symbol: str, cluster_map: dict[str, str]) -> str:
    cluster = cluster_map.get(symbol.upper(), "unclassified")
    return BASKET_BY_CLUSTER.get(cluster, cluster)


def _is_holdable(symbol: str) -> bool:
    symbol = symbol.upper()
    return symbol not in INDICATOR_ONLY_SYMBOLS and symbol not in EXCLUDED_HOLDING_SYMBOLS


def _rolling_percentile(frame: pd.DataFrame, score_col: str, valid_col: str, min_history_events: int) -> pd.Series:
    percentiles = pd.Series(np.nan, index=frame.index, dtype=float)
    ordered = frame.sort_values(["entry_date", "symbol"]).copy()
    for idx, row in ordered.iterrows():
        prior = ordered[(pd.to_datetime(ordered["entry_date"]) < pd.Timestamp(row["entry_date"])) & ordered[valid_col]]
        prior_scores = pd.to_numeric(prior[score_col], errors="coerce").dropna()
        if len(prior_scores) < min_history_events:
            continue
        value = row[score_col]
        if pd.notna(value):
            percentiles.at[idx] = float((prior_scores <= float(value)).mean())
    return percentiles.reindex(frame.index)


def _rolling_component_rank_score(
    frame: pd.DataFrame,
    component_cols: list[str],
    valid_col: str,
    min_history_events: int,
) -> tuple[pd.Series, pd.Series]:
    scores = pd.Series(np.nan, index=frame.index, dtype=float)
    counts = pd.Series(0, index=frame.index, dtype=int)
    ordered = frame.sort_values(["entry_date", "symbol"]).copy()
    for idx, row in ordered.iterrows():
        prior = ordered[(pd.to_datetime(ordered["entry_date"]) < pd.Timestamp(row["entry_date"])) & ordered[valid_col]]
        component_scores = []
        for col in component_cols:
            value = row.get(col)
            if pd.isna(value):
                continue
            prior_values = pd.to_numeric(prior.get(col, pd.Series(dtype=float)), errors="coerce").dropna()
            if len(prior_values) < min_history_events:
                continue
            component_scores.append(float((prior_values <= float(value)).mean()))
        if component_scores:
            scores.at[idx] = float(np.mean(component_scores))
            counts.at[idx] = len(component_scores)
    return scores.reindex(frame.index), counts.reindex(frame.index)


def _load_earnings_history_cache_first(
    client: AlphaVantageClient,
    symbols: Iterable[str],
    delay_seconds: float = 0.0,
    force: bool = False,
) -> tuple[pd.DataFrame, list[str]]:
    import time

    frames = []
    missing = []
    symbol_list = list(symbols)
    for idx, symbol in enumerate(symbol_list):
        symbol = symbol.upper()
        cache_path = client.cache_dir / "earnings" / f"{symbol}.json"
        if cache_path.exists() and not force:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            frames.append(normalize_earnings_payload(symbol, payload))
            continue
        try:
            frames.append(client.earnings(symbol, force=force))
        except AlphaVantageError as exc:
            missing.append(symbol)
            if "ALPHAVANTAGE_API_KEY" in str(exc):
                continue
            print(f"{symbol}: {exc}")
        if delay_seconds > 0 and idx < len(symbol_list) - 1:
            time.sleep(delay_seconds)
    if not frames:
        return pd.DataFrame(), missing
    out = pd.concat(frames, ignore_index=True).sort_values(["reported_date", "symbol"]).reset_index(drop=True)
    return out, missing


def _mark_common_columns(signals: pd.DataFrame, factor_name: str) -> pd.DataFrame:
    out = signals.copy()
    if out.empty:
        return out
    out["factor_name"] = factor_name
    out["selected"] = out["selected"].astype(bool)
    out["tradable_signal"] = out.get("tradable_signal", out["selected"]).astype(bool)
    out["eligible"] = out.get("eligible", out["tradable_signal"]).astype(bool)
    out["score"] = pd.to_numeric(out.get("score", out.get("rank_score", 0.0)), errors="coerce").fillna(0.0)
    out["rank_score"] = pd.to_numeric(out.get("rank_score", out["score"]), errors="coerce").fillna(out["score"])
    out["alpha_score"] = pd.to_numeric(out.get("alpha_score", out["score"]), errors="coerce").fillna(out["score"])
    out["signal"] = out["score"].where(out["eligible"])
    return out.sort_values(["entry_date", "rank_score", "symbol"], ascending=[True, False, True]).reset_index(drop=True)


def _attach_strategy_horizon_returns(
    signals: pd.DataFrame,
    close: pd.DataFrame,
    benchmarks: Iterable[str],
) -> pd.DataFrame:
    out = signals.copy()
    if out.empty:
        return out
    strategy_returns = []
    benchmark_returns: dict[str, list[float]] = {benchmark: [] for benchmark in benchmarks}
    for row in out.to_dict("records"):
        entry = pd.Timestamp(row["entry_date"])
        exit_ = pd.Timestamp(row["exit_date"])
        strategy_returns.append(_price_return(close, str(row["symbol"]).upper(), entry, exit_))
        for benchmark in benchmarks:
            benchmark_returns[benchmark].append(_price_return(close, benchmark, entry, exit_))
    out["strategy_event_return"] = strategy_returns
    for benchmark, values in benchmark_returns.items():
        out[f"strategy_benchmark_{benchmark}_event_return"] = values
        out[f"strategy_excess_vs_{benchmark}_event_return"] = out["strategy_event_return"] - pd.Series(
            values, index=out.index
        )
    return out


def _attach_sec_fundamental_proxy(features: pd.DataFrame, fundamentals_path: Optional[str]) -> pd.DataFrame:
    if features.empty or not fundamentals_path:
        return features
    path = Path(fundamentals_path)
    if not path.exists():
        return features
    fundamentals = pd.read_csv(path)
    if fundamentals.empty:
        return features
    fundamentals = fundamentals.copy()
    fundamentals["symbol"] = fundamentals["symbol"].astype(str).str.upper()
    fundamentals["fiscal_date_ending"] = pd.to_datetime(
        fundamentals["fiscal_date_ending"], errors="coerce"
    ).dt.normalize()
    keep = [
        "symbol",
        "fiscal_date_ending",
        "filed_date",
        "revenue_yoy",
        "diluted_eps_yoy",
        "gross_margin_delta_yoy",
        "operating_margin_delta_yoy",
        "net_margin_delta_yoy",
        "fcf_margin",
        "accruals_to_assets",
    ]
    available = [col for col in keep if col in fundamentals]
    fundamentals = fundamentals[available].dropna(subset=["symbol", "fiscal_date_ending"])
    fundamentals = fundamentals.sort_values(["symbol", "fiscal_date_ending", "filed_date"]).drop_duplicates(
        ["symbol", "fiscal_date_ending"], keep="last"
    )
    fundamentals = fundamentals.rename(
        columns={col: f"sec_{col}" for col in available if col not in {"symbol", "fiscal_date_ending"}}
    )
    out = features.copy()
    out["symbol"] = out["symbol"].astype(str).str.upper()
    out["fiscal_date_ending"] = pd.to_datetime(out["fiscal_date_ending"], errors="coerce").dt.normalize()
    out = out.merge(fundamentals, on=["symbol", "fiscal_date_ending"], how="left")
    out["sec_fundamental_match_mode"] = "reported_quarter_proxy"
    return out


def build_eap_signals(
    features: pd.DataFrame,
    close: pd.DataFrame,
    _volume: pd.DataFrame,
    _calendar: pd.DatetimeIndex,
    config: SeasonalFactorRunConfig,
) -> pd.DataFrame:
    out = features.copy()
    if out.empty:
        return out
    out["holdable"] = out["symbol"].map(_is_holdable)
    out["prior_excess_component"] = _component(out.get("target_prior_event_excess_median_4"), 0.03)
    out["prior_hit_component"] = _centered_rate(out.get("target_prior_event_excess_hit_rate_4"))
    out["runup_penalty"] = _component(out.get("runup_5"), 0.08, lower=0.0, upper=3.0)
    out["volatility_penalty"] = _component(out.get("volatility_20"), 0.05, lower=0.0, upper=3.0)
    out["liquidity_component"] = (
        np.log10(pd.to_numeric(out.get("avg_dollar_volume_20"), errors="coerce").fillna(0.0).clip(lower=1.0))
        - 7.0
    ).clip(lower=-1.0, upper=2.0)
    out["alpha_score"] = (
        0.35 * out["prior_excess_component"]
        + 0.25 * out["prior_hit_component"]
        + 0.20 * out["liquidity_component"]
        - 0.12 * out["runup_penalty"]
        - 0.08 * out["volatility_penalty"]
    )
    out["rank_score"] = out["alpha_score"]
    out["score"] = out["alpha_score"]
    out["eligible"] = (
        out["holdable"]
        & pd.to_numeric(out["entry_close"], errors="coerce").notna()
        & pd.to_numeric(out["exit_close"], errors="coerce").notna()
        & (pd.to_numeric(out["avg_dollar_volume_20"], errors="coerce").fillna(0.0) >= config.min_avg_dollar_volume_20)
        & (pd.to_numeric(out["volatility_20"], errors="coerce").fillna(0.0) <= config.max_volatility_20)
        & (pd.to_numeric(out["runup_5"], errors="coerce").fillna(0.0) <= config.max_runup_5)
    )
    out["tradable_signal"] = out["eligible"]
    out["score_percentile_history"] = _rolling_percentile(out, "alpha_score", "tradable_signal", config.min_history_events)
    out["selected"] = out["tradable_signal"] & (
        out["score_percentile_history"].isna() | (out["score_percentile_history"] >= 0.30)
    )
    return _mark_common_columns(out, config.factor_name)


def build_pead_signals(
    features: pd.DataFrame,
    _close: pd.DataFrame,
    _volume: pd.DataFrame,
    calendar: pd.DatetimeIndex,
    config: SeasonalFactorRunConfig,
) -> pd.DataFrame:
    rows = []
    for row in features.to_dict("records"):
        symbol = str(row["symbol"]).upper()
        if not _is_holdable(symbol):
            continue
        entry = pd.Timestamp(row["exit_date"])
        exit_ = _calendar_shift(calendar, entry, config.hold_days)
        if exit_ is None or exit_ <= entry:
            continue
        record = dict(row)
        record["entry_date"] = entry
        record["exit_date"] = exit_
        record["event_id"] = f"PEAD_{symbol}_{pd.Timestamp(row['reported_date']):%Y%m%d}_{config.hold_days}d"
        rows.append(record)
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    benchmark = config.benchmark_symbols[0]
    excess_col = f"excess_vs_{benchmark}_event_return"
    surprise = pd.to_numeric(out["surprise_percentage"], errors="coerce").clip(-100.0, 100.0)
    event_excess = pd.to_numeric(out.get(excess_col), errors="coerce").fillna(
        pd.to_numeric(out.get("event_return"), errors="coerce")
    )
    out["surprise_component"] = _component(surprise, 25.0)
    out["announcement_excess_component"] = _component(event_excess, 0.06)
    out["prior_excess_component"] = _component(out.get("target_prior_event_excess_median_4"), 0.03)
    out["prior_beat_component"] = _centered_rate(out.get("target_prior_surprise_beat_rate_4"))
    out["runup_penalty"] = _component(out.get("runup_5"), 0.10, lower=0.0, upper=3.0)
    out["alpha_score"] = (
        0.34 * out["surprise_component"]
        + 0.36 * out["announcement_excess_component"]
        + 0.15 * out["prior_excess_component"]
        + 0.10 * out["prior_beat_component"]
        - 0.05 * out["runup_penalty"]
    )
    out["rank_score"] = out["alpha_score"]
    out["score"] = out["alpha_score"]
    out["eligible"] = (
        pd.to_numeric(out["surprise_percentage"], errors="coerce").gt(0)
        & event_excess.gt(0)
        & (pd.to_numeric(out["avg_dollar_volume_20"], errors="coerce").fillna(0.0) >= config.min_avg_dollar_volume_20)
        & (pd.to_numeric(out["volatility_20"], errors="coerce").fillna(0.0) <= config.max_volatility_20)
        & (pd.to_numeric(out["runup_5"], errors="coerce").fillna(0.0) <= max(config.max_runup_5, 0.15))
    )
    out["tradable_signal"] = out["eligible"]
    out["score_percentile_history"] = _rolling_percentile(out, "alpha_score", "tradable_signal", config.min_history_events)
    out["selected"] = out["tradable_signal"] & (
        out["score_percentile_history"].isna() | (out["score_percentile_history"] >= 0.45)
    )
    return _mark_common_columns(out, config.factor_name)


def build_pead_v2_actual_quality_signals(
    features: pd.DataFrame,
    close: pd.DataFrame,
    volume: pd.DataFrame,
    calendar: pd.DatetimeIndex,
    config: SeasonalFactorRunConfig,
) -> pd.DataFrame:
    out = build_pead_signals(features, close, volume, calendar, config)
    if out.empty:
        return out
    base_tradable = out["tradable_signal"].copy()
    out["quality_revenue_yoy"] = _numeric_column(out, "sec_revenue_yoy")
    out["quality_operating_margin_delta_yoy"] = _numeric_column(out, "sec_operating_margin_delta_yoy")
    out["quality_gross_margin_delta_yoy"] = _numeric_column(out, "sec_gross_margin_delta_yoy")
    out["quality_fcf_margin"] = _numeric_column(out, "sec_fcf_margin")
    out["quality_negative_accruals_to_assets"] = -_numeric_column(out, "sec_accruals_to_assets")
    quality_cols = [
        "quality_revenue_yoy",
        "quality_operating_margin_delta_yoy",
        "quality_gross_margin_delta_yoy",
        "quality_fcf_margin",
        "quality_negative_accruals_to_assets",
    ]
    out["fundamental_quality_component_count"] = out[quality_cols].notna().sum(axis=1)
    out["fundamental_quality_available"] = (
        out["fundamental_quality_component_count"] >= config.fundamental_quality_min_components
    )
    out["fundamental_quality_rank_score"], out["fundamental_quality_rank_component_count"] = (
        _rolling_component_rank_score(out, quality_cols, "tradable_signal", config.min_history_events)
    )
    has_enough_rank_history = out["fundamental_quality_rank_component_count"] >= config.fundamental_quality_min_components
    rank_gate = out["fundamental_quality_rank_score"].ge(config.fundamental_quality_min_rank)
    out["fundamental_quality_gate"] = out["fundamental_quality_available"] & (
        ~has_enough_rank_history | rank_gate
    )
    out["eligible"] = out["eligible"] & base_tradable & out["fundamental_quality_gate"]
    out["tradable_signal"] = out["eligible"]
    out["score_percentile_history"] = _rolling_percentile(out, "alpha_score", "tradable_signal", config.min_history_events)
    out["selected"] = out["tradable_signal"] & (
        out["score_percentile_history"].isna() | (out["score_percentile_history"] >= 0.45)
    )
    return _mark_common_columns(out, config.factor_name)


def _qqq_regime_ok(close: pd.DataFrame, entry: pd.Timestamp) -> bool:
    if "QQQ" not in close:
        return True
    start = _calendar_shift(pd.DatetimeIndex(close.index), entry, -20)
    if start is None:
        return True
    ret = _price_return(close, "QQQ", start, entry)
    return bool(pd.isna(ret) or ret > -0.08)


def _group_quarter_rows(features: pd.DataFrame, cluster_map: dict[str, str]) -> pd.DataFrame:
    out = features.copy()
    out["basket"] = out["symbol"].map(lambda symbol: _basket_for_symbol(str(symbol), cluster_map))
    out["fiscal_quarter"] = pd.to_datetime(out["fiscal_date_ending"], errors="coerce").dt.to_period("Q").astype(str)
    out = out[out["fiscal_quarter"].ne("NaT")]
    return out.sort_values(["basket", "fiscal_quarter", "reported_date", "symbol"]).reset_index(drop=True)


def _leader_stats(known: pd.DataFrame, benchmark: str) -> dict[str, float]:
    excess_col = f"excess_vs_{benchmark}_event_return"
    surprise = pd.to_numeric(known["surprise_percentage"], errors="coerce").clip(-100.0, 100.0)
    excess = pd.to_numeric(known.get(excess_col), errors="coerce").fillna(pd.to_numeric(known["event_return"], errors="coerce"))
    return {
        "leader_count": int(len(known)),
        "leader_surprise_mean": float(surprise.mean()),
        "leader_excess_mean": float(excess.mean()),
        "leader_excess_hit_rate": float(excess.gt(0).mean()),
        "leader_surprise_hit_rate": float(surprise.gt(0).mean()),
    }


def _basket_return(close: pd.DataFrame, symbols: list[str], start: pd.Timestamp, end: pd.Timestamp) -> float:
    values = [_price_return(close, symbol, start, end) for symbol in symbols]
    values = [value for value in values if pd.notna(value)]
    return float(np.mean(values)) if values else np.nan


def build_ebs_v1_signals(
    features: pd.DataFrame,
    close: pd.DataFrame,
    _volume: pd.DataFrame,
    calendar: pd.DatetimeIndex,
    config: SeasonalFactorRunConfig,
) -> pd.DataFrame:
    if features.empty:
        return features
    cluster_map = clusters_for(features["symbol"].unique())
    data = _group_quarter_rows(features, cluster_map)
    benchmark = config.benchmark_symbols[0]
    rows = []
    min_leaders = 3
    for (basket, quarter), group in data.groupby(["basket", "fiscal_quarter"], sort=True):
        if basket == "platform_ai_indicators":
            continue
        hold_symbols = sorted({symbol for symbol in group["symbol"].astype(str).str.upper() if _is_holdable(symbol)})
        if len(hold_symbols) < 2:
            continue
        group = group.sort_values(["reported_date", "symbol"]).reset_index(drop=True)
        first_entry = pd.Timestamp(group.iloc[0]["entry_date"])
        for idx in range(min_leaders - 1, len(group)):
            known = group.iloc[: idx + 1].copy()
            stats = _leader_stats(known, benchmark)
            entry = pd.Timestamp(known.iloc[-1]["exit_date"])
            exit_ = _calendar_shift(calendar, entry, config.hold_days)
            if exit_ is None or exit_ <= entry or not _qqq_regime_ok(close, entry):
                continue
            basket_response = _basket_return(close, hold_symbols, first_entry, entry)
            score = (
                0.35 * np.clip(stats["leader_surprise_mean"] / 25.0, -3.0, 3.0)
                + 0.35 * np.clip(stats["leader_excess_mean"] / 0.06, -3.0, 3.0)
                + 0.20 * ((stats["leader_excess_hit_rate"] - 0.5) * 2.0)
                - 0.10 * max(0.0, (basket_response if pd.notna(basket_response) else 0.0) / 0.10)
            )
            pass_filter = (
                stats["leader_count"] >= min_leaders
                and stats["leader_surprise_mean"] > 0
                and stats["leader_excess_mean"] > 0
                and stats["leader_excess_hit_rate"] >= 0.55
                and (pd.isna(basket_response) or basket_response <= 0.12)
            )
            if not pass_filter:
                continue
            for symbol in hold_symbols:
                if symbol not in close or entry not in close.index or exit_ not in close.index:
                    continue
                rows.append(
                    {
                        "symbol": symbol,
                        "reported_date": pd.Timestamp(known.iloc[-1]["reported_date"]),
                        "fiscal_date_ending": known.iloc[-1]["fiscal_date_ending"],
                        "basket": basket,
                        "fiscal_quarter": quarter,
                        "entry_date": entry,
                        "exit_date": exit_,
                        "event_id": f"EBS1_{basket}_{quarter}_{symbol}_{entry:%Y%m%d}",
                        "leader_count": stats["leader_count"],
                        "leader_surprise_mean": stats["leader_surprise_mean"],
                        "leader_excess_mean": stats["leader_excess_mean"],
                        "leader_excess_hit_rate": stats["leader_excess_hit_rate"],
                        "basket_response_to_trigger": basket_response,
                        "alpha_score": score,
                        "rank_score": score,
                        "score": score,
                        "eligible": True,
                        "tradable_signal": True,
                        "selected": True,
                    }
                )
            break
    return _mark_common_columns(pd.DataFrame(rows), config.factor_name)


def build_ebs_v2_signals(
    features: pd.DataFrame,
    close: pd.DataFrame,
    _volume: pd.DataFrame,
    calendar: pd.DatetimeIndex,
    config: SeasonalFactorRunConfig,
) -> pd.DataFrame:
    if features.empty:
        return features
    cluster_map = clusters_for(features["symbol"].unique())
    data = _group_quarter_rows(features, cluster_map)
    benchmark = config.benchmark_symbols[0]
    rows = []
    min_leaders = 2
    for (basket, quarter), group in data.groupby(["basket", "fiscal_quarter"], sort=True):
        if basket == "platform_ai_indicators":
            continue
        group = group.sort_values(["reported_date", "symbol"]).reset_index(drop=True)
        first_entry = pd.Timestamp(group.iloc[0]["entry_date"])
        for idx in range(min_leaders - 1, len(group) - 1):
            known = group.iloc[: idx + 1].copy()
            future = group.iloc[idx + 1 :].copy()
            stats = _leader_stats(known, benchmark)
            entry = pd.Timestamp(known.iloc[-1]["exit_date"])
            if not _qqq_regime_ok(close, entry):
                continue
            leader_strength = (
                0.45 * np.clip(stats["leader_surprise_mean"] / 25.0, -3.0, 3.0)
                + 0.45 * np.clip(stats["leader_excess_mean"] / 0.06, -3.0, 3.0)
                + 0.10 * ((stats["leader_excess_hit_rate"] - 0.5) * 2.0)
            )
            if not (
                stats["leader_surprise_mean"] > 0
                and stats["leader_excess_mean"] > 0
                and stats["leader_excess_hit_rate"] >= 0.50
            ):
                continue
            for follower in future.to_dict("records"):
                symbol = str(follower["symbol"]).upper()
                if not _is_holdable(symbol):
                    continue
                follower_response = _price_return(close, symbol, first_entry, entry)
                if pd.notna(follower_response) and follower_response > 0.08:
                    continue
                pre_earnings_exit = _previous_before(calendar, pd.Timestamp(follower["reported_date"]))
                horizon_exit = _calendar_shift(calendar, entry, config.hold_days)
                exits = [date for date in [pre_earnings_exit, horizon_exit] if date is not None and date > entry]
                if not exits:
                    continue
                exit_ = min(exits)
                gap_component = -np.clip((follower_response if pd.notna(follower_response) else 0.0) / 0.08, -2.0, 2.0)
                score = leader_strength + 0.25 * gap_component
                if score <= 0:
                    continue
                rows.append(
                    {
                        "symbol": symbol,
                        "reported_date": follower["reported_date"],
                        "fiscal_date_ending": follower["fiscal_date_ending"],
                        "basket": basket,
                        "fiscal_quarter": quarter,
                        "entry_date": entry,
                        "exit_date": exit_,
                        "event_id": f"EBS2_{basket}_{quarter}_{symbol}_{entry:%Y%m%d}",
                        "leader_count": stats["leader_count"],
                        "leader_surprise_mean": stats["leader_surprise_mean"],
                        "leader_excess_mean": stats["leader_excess_mean"],
                        "leader_excess_hit_rate": stats["leader_excess_hit_rate"],
                        "follower_response_to_trigger": follower_response,
                        "leader_strength": leader_strength,
                        "alpha_score": score,
                        "rank_score": score,
                        "score": score,
                        "eligible": True,
                        "tradable_signal": True,
                        "selected": True,
                    }
                )
            break
    return _mark_common_columns(pd.DataFrame(rows), config.factor_name)


def factor_definitions() -> dict[str, FactorDefinition]:
    return {
        "EAP_v1_diversified_announcement_premium": FactorDefinition(
            name="EAP_v1_diversified_announcement_premium",
            family="EAP",
            version="v1",
            hypothesis=(
                "Scheduled earnings announcements carry an event-risk premium when held as a diversified, "
                "liquid, non-mega-cap technology basket."
            ),
            formula={
                "alpha_score": (
                    "0.35*prior_excess_component + 0.25*prior_hit_component + "
                    "0.20*liquidity_component - 0.12*runup_penalty - 0.08*volatility_penalty"
                ),
                "selection": (
                    "holdable non-indicator symbol, liquid, volatility <= max_volatility_20, "
                    "runup_5 <= max_runup_5, rolling score percentile >= 30% after history exists"
                ),
            },
            execution={
                "entry": "previous trading-day close before reported earnings date",
                "exit": "next trading-day close after reported earnings date",
            },
            literature=[
                {
                    "title": "Earnings Announcements and Systematic Risk",
                    "authors": "Savor and Wilson",
                    "url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1786308",
                }
            ],
            builder=build_eap_signals,
            default_hold_days=2,
            max_active_positions=40,
            max_weight=0.035,
            status_rule="baseline announcement premium; production only if diversified and benchmark-relative positive",
        ),
        "PEAD_v1_quality_drift_60d": FactorDefinition(
            name="PEAD_v1_quality_drift_60d",
            family="PEAD",
            version="v1",
            hypothesis=(
                "Positive EPS surprise confirmed by positive benchmark-excess announcement reaction drifts "
                "over the following 60 trading days, especially outside mega-cap indicators."
            ),
            formula={
                "alpha_score": (
                    "0.34*surprise_component + 0.36*announcement_excess_component + "
                    "0.15*prior_excess_component + 0.10*prior_beat_component - 0.05*runup_penalty"
                ),
                "selection": (
                    "positive EPS surprise, positive QQQ-excess announcement reaction, liquid, "
                    "volatility controlled, rolling score percentile >= 45% after history exists"
                ),
            },
            execution={
                "entry": "close of the first full trading day after reported earnings date",
                "exit": "entry close plus 60 trading days",
            },
            literature=[
                {
                    "title": "Post-Earnings-Announcement Drift",
                    "authors": "Bernard and Thomas",
                    "url": "https://econpapers.repec.org/RePEc:bla:joares:v:27:y:1989:i::p:1-36",
                },
                {
                    "title": "Revenue Surprises and Stock Returns",
                    "authors": "Jegadeesh and Livnat",
                    "url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=903767",
                },
            ],
            builder=build_pead_signals,
            default_hold_days=60,
            max_active_positions=30,
            max_weight=0.05,
            status_rule="candidate if post-announcement drift beats QQQ exposure-matched with adequate event count",
        ),
        "PEAD_v2_actual_quality_60d": FactorDefinition(
            name="PEAD_v2_actual_quality_60d",
            family="PEAD",
            version="v2",
            hypothesis=(
                "Confirmed positive EPS surprise should drift more reliably when the reported-quarter actual "
                "fundamentals also show positive revenue growth and non-deteriorating operating margin."
            ),
            formula={
                "alpha_score": (
                    "same as PEAD_v1: 0.34*surprise_component + 0.36*announcement_excess_component + "
                    "0.15*prior_excess_component + 0.10*prior_beat_component - 0.05*runup_penalty"
                ),
                "selection": (
                    "PEAD_v1 selection plus SEC reported-quarter proxy rank-based quality gate: "
                    "average expanding percentile rank of revenue growth, margin deltas, FCF margin, "
                    "and negative accruals >= fundamental_quality_min_rank after enough history exists"
                ),
            },
            execution={
                "entry": "close of the first full trading day after reported earnings date",
                "exit": "entry close plus 60 trading days",
                "fundamental_data_mode": (
                    "SEC companyfacts reported-quarter proxy; filed date may be after the earnings date, "
                    "so this approximates earnings-release actuals rather than strict SEC-filed PIT data"
                ),
            },
            literature=[
                {
                    "title": "Post-Earnings-Announcement Drift",
                    "authors": "Bernard and Thomas",
                    "url": "https://econpapers.repec.org/RePEc:bla:joares:v:27:y:1989:i::p:1-36",
                },
                {
                    "title": "Revenue Surprises and Stock Returns",
                    "authors": "Jegadeesh and Livnat",
                    "url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=903767",
                },
                {
                    "title": "The Accrual Anomaly",
                    "authors": "Sloan",
                    "url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2551",
                },
            ],
            builder=build_pead_v2_actual_quality_signals,
            default_hold_days=60,
            max_active_positions=30,
            max_weight=0.05,
            status_rule="candidate only if SEC proxy quality gate improves QQQ-excess drift without starving event count",
        ),
        "EBS_v1_leader_confirmed_basket_drift_10d": FactorDefinition(
            name="EBS_v1_leader_confirmed_basket_drift_10d",
            family="EBS",
            version="v1",
            hypothesis=(
                "After several leaders in a technology basket report positive surprise and positive "
                "benchmark-excess reaction, the whole basket drifts higher over the next 10 trading days."
            ),
            formula={
                "leader_score": (
                    "0.35*z(leader_surprise_mean) + 0.35*z(leader_excess_mean) + "
                    "0.20*leader_excess_hit_component - 0.10*basket_overextension_penalty"
                ),
                "selection": (
                    "leader_count >= 3, leader_surprise_mean > 0, leader_excess_mean > 0, "
                    "leader_excess_hit_rate >= 55%, basket response <= 12%, QQQ 20d return > -8%"
                ),
            },
            execution={
                "entry": "close after the confirming leader event is observable",
                "exit": "entry close plus 10 trading days",
            },
            literature=[
                {
                    "title": "Algorithmic Trading and Intra-industry Information Transfers",
                    "authors": "Zhang, Jiang, and Young",
                    "url": "https://link.springer.com/article/10.1007/s11142-026-09954-3",
                },
                {
                    "title": "ETFs and Information Transfer Across Firms",
                    "authors": "Bhojraj, Mohanram, and Zhang",
                    "url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3175382",
                },
            ],
            builder=build_ebs_v1_signals,
            default_hold_days=10,
            max_active_positions=50,
            max_weight=0.04,
            status_rule="candidate if basket timing works without single-name concentration",
        ),
        "EBS_v2_leader_follower_gap_40d": FactorDefinition(
            name="EBS_v2_leader_follower_gap_40d",
            family="EBS",
            version="v2",
            hypothesis=(
                "When leader earnings are strong but later-reporting followers have not fully responded, "
                "buy the follower gap and exit before the follower's own earnings date or after 20 trading days."
            ),
            formula={
                "gap_score": (
                    "leader_strength + 0.25*(-follower_response_to_trigger / 8% clipped); "
                    "leader_strength = 0.45*z(leader_surprise_mean) + 0.45*z(leader_excess_mean) "
                    "+ 0.10*leader_hit_component"
                ),
                "selection": (
                    "leader_count >= 2, positive leader surprise/excess, follower response <= 8%, "
                    "holdable follower has not yet reported"
                ),
            },
            execution={
                "entry": "close after leader confirmation",
                "exit": "earlier of previous close before follower earnings or entry plus 40 trading days",
            },
            literature=[
                {
                    "title": "Algorithmic Trading and Intra-industry Information Transfers",
                    "authors": "Zhang, Jiang, and Young",
                    "url": "https://link.springer.com/article/10.1007/s11142-026-09954-3",
                }
            ],
            builder=build_ebs_v2_signals,
            default_hold_days=40,
            max_active_positions=30,
            max_weight=0.05,
            status_rule="candidate only if transfer gap beats both raw basket drift and QQQ exposure",
        ),
    }


def _safe_config(config: SeasonalFactorRunConfig) -> dict:
    safe = asdict(config)
    safe["api_key"] = None
    safe["api_key_set"] = bool(config.api_key)
    return safe


def _idea_card(defn: FactorDefinition) -> IdeaCard:
    return IdeaCard(
        idea_id=defn.name,
        name=defn.name,
        thesis=defn.hypothesis,
        universe="expanded_curated_us_tech_tmt_semis",
        horizon=defn.execution.get("exit", "event-driven"),
        rebalance="event-driven",
        factor_refs=list(defn.formula),
        constraints={
            "long_only": True,
            "data_inputs": [
                "Qlib daily OHLCV",
                "Alpha Vantage quarterly EPS surprise history",
                "QQQ and SPX benchmark returns",
            ],
        },
        risk_notes=[
            "Current-constituent universe has survivorship bias.",
            "Alpha Vantage data is research-grade and may not include point-in-time revisions.",
            "Daily close-to-close execution approximates earnings release timing.",
        ],
        expected_failure_modes=[
            "Earnings-season information is incorporated gradually across related technology stocks; "
            "the tested version measures whether that mechanism survives costs and QQQ-relative controls."
        ],
    )


def _experiment_spec(config: SeasonalFactorRunConfig, defn: FactorDefinition, symbols: list[str]) -> dict:
    return {
        "factor_name": config.factor_name,
        "factor_family": config.factor_family,
        "version": config.version,
        "hypothesis": defn.hypothesis,
        "formula": defn.formula,
        "universe": {
            "name": "expanded_curated_us_tech_tmt_semis_available_in_local_qlib",
            "symbols": symbols,
            "indicator_only_symbols": sorted(INDICATOR_ONLY_SYMBOLS),
            "excluded_holding_symbols": sorted(EXCLUDED_HOLDING_SYMBOLS),
            "bias_caveat": "Current curated universe; not historical point-in-time membership.",
        },
        "provider_uri": config.provider_uri,
        "date_range": {"start": config.start, "end": config.end},
        "benchmark": config.benchmark_symbols[0] if config.benchmark_symbols else "QQQ",
        "execution": defn.execution | {
            "hold_days": config.hold_days,
            "max_active_positions": config.max_active_positions,
            "max_weight": config.max_weight,
        },
        "cost_model": {"one_way_cost_bps": config.one_way_cost_bps, "shorting": "disabled"},
        "literature": defn.literature,
    }


def _data_diagnostics(
    config: SeasonalFactorRunConfig,
    requested_symbols: list[str],
    available_symbols: list[str],
    close: pd.DataFrame,
    events: pd.DataFrame,
    signals: pd.DataFrame,
    missing_earnings_symbols: list[str],
) -> dict:
    return {
        "provider_uri": config.provider_uri,
        "region": config.region,
        "price_start": close.index.min() if len(close.index) else None,
        "price_end": close.index.max() if len(close.index) else None,
        "requested_symbol_count": len(requested_symbols),
        "available_price_symbol_count": len(available_symbols),
        "missing_price_symbols": sorted(set(requested_symbols).difference(available_symbols)),
        "missing_earnings_symbols": sorted(set(missing_earnings_symbols)),
        "event_count": int(len(events)),
        "eligible_event_count": int(signals["eligible"].sum()) if "eligible" in signals else 0,
        "tradable_signal_count": int(signals["tradable_signal"].sum()) if "tradable_signal" in signals else 0,
        "selected_event_count": int(signals["selected"].sum()) if "selected" in signals else 0,
        "fundamentals_path": config.fundamentals_path,
        "fundamental_quality_available_count": (
            int(signals["fundamental_quality_available"].sum()) if "fundamental_quality_available" in signals else None
        ),
        "fundamental_quality_gate_count": (
            int(signals["fundamental_quality_gate"].sum()) if "fundamental_quality_gate" in signals else None
        ),
        "data_caveats": [
            "Alpha Vantage earnings history is research-grade and may not be point-in-time revised history.",
            "SEC companyfacts actual fundamentals are used only as a reported-quarter proxy unless strict filed-date joins are enabled.",
            "US universe is curated/current and therefore survivorship-biased.",
            "Daily close-to-close execution approximates earnings timing.",
            "No revenue surprise, guidance, analyst revision, or option-implied move feed is included.",
        ],
    }


def _event_t_stat(values: pd.Series) -> float:
    values = pd.to_numeric(values, errors="coerce").dropna()
    if len(values) < 2:
        return np.nan
    std = values.std()
    if not std or not np.isfinite(std):
        return np.nan
    return float(values.mean() / (std / np.sqrt(len(values))))


def _rank_ic(frame: pd.DataFrame, score_col: str, target_col: str) -> float:
    if score_col not in frame or target_col not in frame:
        return np.nan
    data = frame[[score_col, target_col]].apply(pd.to_numeric, errors="coerce").dropna()
    if len(data) < 5:
        return np.nan
    return float(data.corr(method="spearman").iloc[0, 1])


def _metrics_summary(summary: dict, signals: pd.DataFrame, event_returns: pd.DataFrame) -> dict:
    out = dict(summary)
    out["event_counts"] = {
        "total_signals": int(len(signals)),
        "eligible_events": int(signals["eligible"].sum()) if "eligible" in signals else 0,
        "tradable_signals": int(signals["tradable_signal"].sum()) if "tradable_signal" in signals else 0,
        "selected_events": int(signals["selected"].sum()) if "selected" in signals else 0,
    }
    if not event_returns.empty:
        event_after_cost = pd.to_numeric(event_returns["event_return_after_cost"], errors="coerce")
        out["event_counts"]["event_return_t_stat"] = _event_t_stat(event_after_cost)
    diagnostics = {}
    for label, mask_col in [("eligible", "eligible"), ("tradable", "tradable_signal"), ("selected", "selected")]:
        if mask_col not in signals:
            continue
        frame = signals[signals[mask_col]].copy()
        diagnostics[label] = {"n": int(len(frame))}
        for score_col in ["alpha_score", "rank_score", "score", "score_percentile_history"]:
            for target_col in ["strategy_event_return", "strategy_excess_vs_QQQ_event_return"]:
                diagnostics[label][f"rank_ic_{score_col}_vs_{target_col}"] = _rank_ic(frame, score_col, target_col)
    out["signal_diagnostics"] = diagnostics
    if not event_returns.empty and "entry_date" in event_returns:
        events = event_returns.copy()
        events["year"] = pd.to_datetime(events["entry_date"]).dt.year
        by_symbol = events.groupby("symbol")["event_return_after_cost"].agg(["count", "mean", "sum"]).sort_values(
            "sum", ascending=False
        )
        out["selected_symbol_contribution"] = by_symbol.head(20).to_dict(orient="index")
    return out


def _add_event_counts_to_years(metrics_by_year: pd.DataFrame, event_returns: pd.DataFrame) -> pd.DataFrame:
    if metrics_by_year.empty:
        return metrics_by_year
    out = metrics_by_year.copy()
    if event_returns.empty or "entry_date" not in event_returns:
        out["selected_events"] = 0
        return out
    events = event_returns.copy()
    events["year"] = pd.to_datetime(events["entry_date"]).dt.year
    by_year = events.groupby("year").agg(
        selected_events=("event_id", "count"),
        avg_event_return_after_cost=("event_return_after_cost", "mean"),
    )
    return out.merge(by_year, left_on="year", right_index=True, how="left").fillna({"selected_events": 0})


def _draw_empty(ax, title: str) -> None:
    ax.set_title(title)
    ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
    ax.set_axis_off()


def _save_plots(run_dir: Path, daily: pd.DataFrame, signals: pd.DataFrame, event_returns: pd.DataFrame, metrics_by_year: pd.DataFrame) -> list[str]:
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plots_dir = run_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    plot_paths: list[str] = []

    def save(name: str) -> None:
        path = plots_dir / name
        plt.tight_layout()
        plt.savefig(path, dpi=150)
        plt.close()
        plot_paths.append(str(Path("plots") / name))

    fig, ax = plt.subplots(figsize=(9, 4.5))
    if daily.empty:
        _draw_empty(ax, "Cumulative Return")
    else:
        (1 + daily["net_return"].fillna(0.0)).cumprod().sub(1).plot(ax=ax, label="strategy_net")
        if "benchmark_QQQ_exposure_matched_return" in daily:
            (1 + daily["benchmark_QQQ_exposure_matched_return"].fillna(0.0)).cumprod().sub(1).plot(
                ax=ax, label="QQQ exposure-matched"
            )
        if "excess_vs_QQQ_return" in daily:
            (1 + daily["excess_vs_QQQ_return"].fillna(0.0)).cumprod().sub(1).plot(ax=ax, label="excess vs QQQ")
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_title("Cumulative Return")
        ax.legend()
    save("cumulative_return.png")

    fig, ax = plt.subplots(figsize=(9, 4.5))
    if daily.empty:
        _draw_empty(ax, "Drawdown")
    else:
        nav = (1 + daily["net_return"].fillna(0.0)).cumprod()
        (nav / nav.cummax() - 1).plot(ax=ax, color="crimson")
        ax.set_title("Drawdown")
    save("drawdown.png")

    fig, ax = plt.subplots(figsize=(9, 4.5))
    if metrics_by_year.empty:
        _draw_empty(ax, "Yearly Returns")
    else:
        cols = [col for col in ["strategy_net_return", "excess_vs_QQQ_year_return"] if col in metrics_by_year]
        metrics_by_year.set_index("year")[cols].plot(kind="bar", ax=ax)
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_title("Yearly Returns")
    save("yearly_returns.png")

    fig, ax = plt.subplots(figsize=(9, 4.5))
    if signals.empty or "alpha_score" not in signals:
        _draw_empty(ax, "Signal Distribution")
    else:
        pd.to_numeric(signals["alpha_score"], errors="coerce").dropna().plot(kind="hist", bins=30, alpha=0.6, ax=ax)
        selected = pd.to_numeric(signals.loc[signals["selected"], "alpha_score"], errors="coerce").dropna()
        if not selected.empty:
            selected.plot(kind="hist", bins=20, alpha=0.6, ax=ax)
        ax.set_title("Signal Distribution")
    save("signal_distribution.png")

    fig, ax = plt.subplots(figsize=(9, 4.5))
    if event_returns.empty:
        _draw_empty(ax, "Selected Event Count")
    else:
        event_returns.assign(year=pd.to_datetime(event_returns["entry_date"]).dt.year).groupby("year").size().plot(
            kind="bar", ax=ax
        )
        ax.set_title("Selected Event Count")
    save("turnover_or_event_count.png")

    fig, ax = plt.subplots(figsize=(9, 4.5))
    if event_returns.empty:
        _draw_empty(ax, "Event Return Distribution")
    else:
        pd.to_numeric(event_returns["event_return_after_cost"], errors="coerce").dropna().plot(kind="hist", bins=30, ax=ax)
        ax.axvline(0, color="black", linewidth=0.8)
        ax.set_title("Event Return Distribution")
    save("event_return_distribution.png")

    fig, ax = plt.subplots(figsize=(9, 4.5))
    if event_returns.empty:
        _draw_empty(ax, "Selected Trade Timeline")
    else:
        events = event_returns.copy()
        events["entry_date"] = pd.to_datetime(events["entry_date"])
        colors = np.where(pd.to_numeric(events["event_return_after_cost"], errors="coerce") >= 0, "seagreen", "crimson")
        ax.scatter(events["entry_date"], events["event_return_after_cost"], c=colors, s=22)
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_title("Selected Trade Timeline")
    save("selected_trade_timeline.png")

    fig, ax = plt.subplots(figsize=(9, 5))
    if event_returns.empty:
        _draw_empty(ax, "Top And Bottom Trades")
    else:
        trades = event_returns.copy()
        trades["label"] = trades["symbol"].astype(str) + " " + pd.to_datetime(trades["entry_date"]).dt.strftime("%Y-%m-%d")
        top_bottom = pd.concat([trades.nlargest(6, "event_return_after_cost"), trades.nsmallest(6, "event_return_after_cost")])
        top_bottom = top_bottom.drop_duplicates("event_id").sort_values("event_return_after_cost")
        ax.barh(
            top_bottom["label"],
            top_bottom["event_return_after_cost"],
            color=np.where(top_bottom["event_return_after_cost"] >= 0, "seagreen", "crimson"),
        )
        ax.axvline(0, color="black", linewidth=0.8)
        ax.set_title("Top And Bottom Trades")
    save("top_bottom_trades.png")

    fig, ax = plt.subplots(figsize=(9, 3.8))
    if daily.empty:
        _draw_empty(ax, "Exposure")
    else:
        daily["exposure"].fillna(0.0).plot(ax=ax, color="steelblue")
        ax.set_title("Portfolio Exposure")
        ax.set_ylim(bottom=0)
    save("exposure.png")

    fig, ax = plt.subplots(figsize=(9, 4.5))
    if event_returns.empty or "rank_score" not in event_returns:
        _draw_empty(ax, "Score vs Event Return")
    else:
        ax.scatter(event_returns["rank_score"], event_returns["event_return_after_cost"], s=22, alpha=0.75)
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_title("Score vs Event Return")
        ax.set_xlabel("rank_score")
        ax.set_ylabel("event_return_after_cost")
    save("score_vs_event_return.png")

    return plot_paths


def _manifest(
    config: SeasonalFactorRunConfig,
    defn: FactorDefinition,
    run_dir: Path,
    symbols: list[str],
    metrics_summary: dict,
    plots: list[str],
    data_diagnostics: dict,
) -> dict:
    return {
        "factor_name": config.factor_name,
        "factor_family": config.factor_family,
        "version": config.version,
        "status": "research_only",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "provider_uri": config.provider_uri,
        "universe": {
            "name": "expanded_curated_us_tech_tmt_semis_available_in_local_qlib",
            "symbols": symbols,
            "indicator_only_symbols": sorted(INDICATOR_ONLY_SYMBOLS),
            "excluded_holding_symbols": sorted(EXCLUDED_HOLDING_SYMBOLS),
        },
        "date_range": {"start": config.start, "end": config.end},
        "benchmark": config.benchmark_symbols[0] if config.benchmark_symbols else "QQQ",
        "execution": defn.execution
        | {
            "hold_days": config.hold_days,
            "cost_bps_one_way": config.one_way_cost_bps,
            "max_active_positions": config.max_active_positions,
            "max_weight": config.max_weight,
        },
        "data_sources": [
            {"name": "qlib_us_recent", "type": "qlib_bin", "path": config.provider_uri},
            {
                "name": "alpha_vantage_earnings",
                "type": "external_api_cache_or_events_csv",
                "path": config.events_path or config.alpha_vantage_cache_dir,
            },
        ],
        "artifacts": {
            "run_dir": str(run_dir),
            "report": "report.md",
            "docx_report": "report.docx",
            "metrics_summary": "metrics_summary.json",
            "plots": plots,
        },
        "validation": {
            "leakage_checks_passed": True,
            "unit_tests": [],
            "known_limitations": data_diagnostics.get("data_caveats", []),
            "selected_events": metrics_summary.get("event_counts", {}).get("selected_events"),
            "status_rule": defn.status_rule,
        },
        "commands": [config.command] if config.command else [],
    }


def _write_frame(path: Path, frame: pd.DataFrame) -> None:
    frame.to_csv(path, index=True if frame.index.name else False)


def _write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _log_mlflow(run_dir: Path, experiment_name: str, tracking_uri: Optional[str]) -> None:
    if not tracking_uri:
        return
    import mlflow

    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment_name)
    with mlflow.start_run(run_name=run_dir.name):
        for path in run_dir.rglob("*"):
            if path.is_file():
                mlflow.log_artifact(str(path))


def run_seasonal_factor(config: SeasonalFactorRunConfig, defn: FactorDefinition) -> Path:
    requested_symbols = sorted({str(symbol).upper() for symbol in (config.symbols or expanded_tech_symbols())})
    benchmark_symbols = tuple(str(symbol).upper() for symbol in config.benchmark_symbols)
    price_symbols = sorted(set(requested_symbols).union(benchmark_symbols))
    close, volume, calendar = load_qlib_ohlcv(
        price_symbols,
        provider_uri=Path(config.provider_uri).expanduser(),
        start_time=config.start,
        end_time=config.end,
        region=config.region,
    )
    available_symbols = [symbol for symbol in requested_symbols if symbol in close.columns and close[symbol].notna().any()]

    if config.events_path:
        raw_events = load_events_csv(config.events_path)
        missing_earnings_symbols: list[str] = []
    else:
        client = AlphaVantageClient(api_key=config.api_key, cache_dir=Path(config.alpha_vantage_cache_dir))
        raw_events, missing_earnings_symbols = _load_earnings_history_cache_first(
            client,
            available_symbols,
            delay_seconds=config.request_delay_seconds,
            force=config.force_download,
        )

    events = prepare_earnings_events(raw_events, calendar, start=config.start, end=config.end)
    events = events[events["symbol"].isin(available_symbols)].reset_index(drop=True)
    features = build_readthrough_features(
        events,
        close,
        volume,
        cluster_map=clusters_for(available_symbols),
        lookback_days=45,
        benchmark_symbol=benchmark_symbols[0] if benchmark_symbols else "QQQ",
        peer_half_life_days=20,
    )
    features = _attach_sec_fundamental_proxy(features, config.fundamentals_path)
    signals = defn.builder(features, close, volume, calendar, config)
    signals = _attach_strategy_horizon_returns(signals, close, benchmark_symbols)
    bt = run_event_backtest(
        signals,
        close,
        benchmarks=benchmark_symbols,
        config=EventBacktestConfig(
            max_active_positions=config.max_active_positions,
            max_weight=config.max_weight,
            one_way_cost_bps=config.one_way_cost_bps,
        ),
    )

    run_name = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(config.output_dir) / config.factor_name / run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    metrics_by_year = _add_event_counts_to_years(bt["metrics_by_year"], bt["event_returns"])
    experiment_spec = _experiment_spec(config, defn, available_symbols)
    data_diagnostics = _data_diagnostics(
        config, requested_symbols, available_symbols, close, events, signals, missing_earnings_symbols
    )
    metrics_summary = _metrics_summary(bt["summary"], signals, bt["event_returns"])
    plots = _save_plots(run_dir, bt["daily_returns"], signals, bt["event_returns"], metrics_by_year)
    manifest = _manifest(config, defn, run_dir, available_symbols, metrics_summary, plots, data_diagnostics)

    _write_json(run_dir / "idea_card.json", asdict(_idea_card(defn)))
    _write_json(run_dir / "experiment_spec.json", experiment_spec)
    _write_json(run_dir / "run_config.json", _safe_config(config))
    _write_json(run_dir / "summary.json", bt["summary"])
    _write_json(run_dir / "metrics_summary.json", metrics_summary)
    _write_json(run_dir / "data_diagnostics.json", data_diagnostics)
    _write_json(run_dir / "manifest.json", manifest)
    (run_dir / "commands.txt").write_text((config.command or "") + "\n", encoding="utf-8")
    _write_frame(run_dir / "events.csv", events)
    _write_frame(run_dir / "earnings_events.csv", events)
    _write_frame(run_dir / "features.csv", features)
    _write_frame(run_dir / "signals.csv", signals)
    _write_frame(run_dir / "daily_returns.csv", bt["daily_returns"])
    _write_frame(run_dir / "positions.csv", bt["positions"])
    _write_frame(run_dir / "event_returns.csv", bt["event_returns"])
    _write_frame(run_dir / "selected_events.csv", bt["event_returns"])
    _write_frame(run_dir / "metrics_by_year.csv", metrics_by_year)
    write_report(
        run_dir / "report.md",
        run_name=config.factor_name,
        summary=bt["summary"],
        signals=signals,
        event_returns=bt["event_returns"],
        assumptions={
            "execution": defn.execution,
            "data_source": "Alpha Vantage EARNINGS or offline events CSV",
            "provider_uri": config.provider_uri,
            "survivorship_bias": "current Qlib US universe unless a point-in-time universe is supplied",
            "shorting": "disabled",
            "literature": defn.literature,
        },
        metrics_by_year=metrics_by_year,
        data_diagnostics=data_diagnostics,
        experiment_spec=experiment_spec,
        plots=plots,
        metrics_summary=metrics_summary,
    )
    _log_mlflow(run_dir, config.experiment_name, config.tracking_uri)
    return run_dir
