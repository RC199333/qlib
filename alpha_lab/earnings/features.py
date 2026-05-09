"""Feature engineering for earnings read-through strategies."""

from __future__ import annotations

from typing import Dict, Iterable

import numpy as np
import pandas as pd


def _safe_get(frame: pd.DataFrame, date: pd.Timestamp, symbol: str) -> float:
    if symbol not in frame.columns or date not in frame.index:
        return np.nan
    return float(frame.at[date, symbol])


def _window_values(series: pd.Series, end_date: pd.Timestamp, window: int) -> pd.Series:
    series = series.dropna()
    series = series[series.index <= end_date]
    return series.tail(window)


def _ret_over_window(series: pd.Series, end_date: pd.Timestamp, window: int) -> float:
    values = _window_values(series, end_date, window + 1)
    if len(values) < window + 1 or values.iloc[0] == 0:
        return np.nan
    return float(values.iloc[-1] / values.iloc[0] - 1)


def _volatility(series: pd.Series, end_date: pd.Timestamp, window: int) -> float:
    values = _window_values(series, end_date, window + 1)
    if len(values) < window + 1:
        return np.nan
    return float(values.pct_change().dropna().std())


def _abnormal_volume(volume: pd.Series, end_date: pd.Timestamp, short: int = 10, long: int = 60) -> float:
    short_values = _window_values(volume, end_date, short)
    long_values = _window_values(volume, end_date, long)
    if len(short_values) < max(3, short // 2) or len(long_values) < max(10, long // 3):
        return np.nan
    long_mean = long_values.mean()
    if not np.isfinite(long_mean) or long_mean <= 0:
        return np.nan
    return float(np.log(short_values.mean() / long_mean))


def _event_return(close: pd.DataFrame, symbol: str, entry: pd.Timestamp, exit_: pd.Timestamp) -> float:
    entry_close = _safe_get(close, entry, symbol)
    exit_close = _safe_get(close, exit_, symbol)
    if pd.isna(entry_close) or pd.isna(exit_close) or entry_close == 0:
        return np.nan
    return float(exit_close / entry_close - 1)


def attach_event_returns(events: pd.DataFrame, close: pd.DataFrame, benchmarks: Iterable[str] = ()) -> pd.DataFrame:
    rows = []
    benchmark_list = [str(symbol).upper() for symbol in benchmarks]
    for row in events.to_dict("records"):
        symbol = row["symbol"]
        entry = pd.Timestamp(row["entry_date"])
        exit_ = pd.Timestamp(row["exit_date"])
        entry_close = _safe_get(close, entry, symbol)
        exit_close = _safe_get(close, exit_, symbol)
        row["entry_close"] = entry_close
        row["exit_close"] = exit_close
        row["event_return"] = _event_return(close, symbol, entry, exit_)
        for benchmark in benchmark_list:
            benchmark_return = _event_return(close, benchmark, entry, exit_)
            row[f"benchmark_{benchmark}_event_return"] = benchmark_return
            row[f"excess_vs_{benchmark}_event_return"] = (
                row["event_return"] - benchmark_return
                if pd.notna(row["event_return"]) and pd.notna(benchmark_return)
                else np.nan
            )
        rows.append(row)
    return pd.DataFrame(rows)


def attach_pre_event_price_features(events: pd.DataFrame, close: pd.DataFrame, volume: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for row in events.to_dict("records"):
        symbol = row["symbol"]
        entry = pd.Timestamp(row["entry_date"])
        close_series = close[symbol] if symbol in close else pd.Series(dtype=float)
        volume_series = volume[symbol] if symbol in volume else pd.Series(dtype=float)
        row["momentum_20"] = _ret_over_window(close_series, entry, 20)
        row["runup_5"] = _ret_over_window(close_series, entry, 5)
        row["volatility_20"] = _volatility(close_series, entry, 20)
        row["abnormal_volume_10"] = _abnormal_volume(volume_series, entry)
        dollar_volume = close_series * volume_series
        row["avg_dollar_volume_20"] = float(_window_values(dollar_volume, entry, 20).mean())
        rows.append(row)
    return pd.DataFrame(rows)


def _weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    valid = pd.to_numeric(values, errors="coerce").notna() & pd.to_numeric(weights, errors="coerce").notna()
    if not valid.any():
        return np.nan
    values = pd.to_numeric(values[valid], errors="coerce")
    weights = pd.to_numeric(weights[valid], errors="coerce")
    weight_sum = weights.sum()
    if not np.isfinite(weight_sum) or weight_sum <= 0:
        return np.nan
    return float((values * weights).sum() / weight_sum)


def _rate(mask: pd.Series) -> float:
    if len(mask) == 0:
        return np.nan
    return float(mask.mean())


def _peer_metrics(peers: pd.DataFrame, benchmark_symbol: str) -> Dict[str, float]:
    if peers.empty:
        return {
            "event_count": 0,
            "surprise_pct_mean": np.nan,
            "surprise_pct_mean_winsor": np.nan,
            "surprise_beat_rate": np.nan,
            "event_return_mean": np.nan,
            "event_excess_mean": np.nan,
            "event_excess_hit_rate": np.nan,
            "positive_readthrough_rate": np.nan,
            "freshness_days_mean": np.nan,
        }

    weights = pd.to_numeric(peers["peer_recency_weight"], errors="coerce")
    surprise = pd.to_numeric(peers["surprise_percentage"], errors="coerce").clip(-100.0, 100.0)
    event_return = pd.to_numeric(peers["event_return"], errors="coerce")
    excess_col = f"excess_vs_{benchmark_symbol}_event_return"
    event_excess = pd.to_numeric(peers[excess_col], errors="coerce") if excess_col in peers else event_return
    surprise_positive = surprise > 0
    excess_positive = event_excess > 0

    return {
        "event_count": int(len(peers)),
        "surprise_pct_mean": float(surprise.mean()) if surprise.notna().any() else np.nan,
        "surprise_pct_mean_winsor": _weighted_mean(surprise, weights),
        "surprise_beat_rate": _rate(surprise_positive.dropna()),
        "event_return_mean": _weighted_mean(event_return, weights),
        "event_excess_mean": _weighted_mean(event_excess, weights),
        "event_excess_hit_rate": _rate(excess_positive.dropna()),
        "positive_readthrough_rate": _rate((surprise_positive & excess_positive).dropna()),
        "freshness_days_mean": _weighted_mean(peers["peer_age_trading_days"], weights),
    }


def _target_history_metrics(history: pd.DataFrame, benchmark_symbol: str, window: int = 4) -> Dict[str, float]:
    history = history.sort_values("exit_date").tail(window)
    if history.empty:
        return {
            "event_count": 0,
            "event_return_mean": np.nan,
            "event_excess_mean": np.nan,
            "event_excess_median": np.nan,
            "event_excess_hit_rate": np.nan,
            "surprise_pct_mean_winsor": np.nan,
            "surprise_beat_rate": np.nan,
        }

    surprise = pd.to_numeric(history["surprise_percentage"], errors="coerce").clip(-100.0, 100.0)
    event_return = pd.to_numeric(history["event_return"], errors="coerce")
    excess_col = f"excess_vs_{benchmark_symbol}_event_return"
    event_excess = pd.to_numeric(history[excess_col], errors="coerce") if excess_col in history else event_return

    return {
        "event_count": int(len(history)),
        "event_return_mean": float(event_return.mean()) if event_return.notna().any() else np.nan,
        "event_excess_mean": float(event_excess.mean()) if event_excess.notna().any() else np.nan,
        "event_excess_median": float(event_excess.median()) if event_excess.notna().any() else np.nan,
        "event_excess_hit_rate": _rate((event_excess > 0).dropna()),
        "surprise_pct_mean_winsor": float(surprise.mean()) if surprise.notna().any() else np.nan,
        "surprise_beat_rate": _rate((surprise > 0).dropna()),
    }


def build_readthrough_features(
    events: pd.DataFrame,
    close: pd.DataFrame,
    volume: pd.DataFrame,
    cluster_map: Dict[str, str],
    lookback_days: int = 45,
    benchmark_symbol: str = "QQQ",
    peer_half_life_days: int = 20,
) -> pd.DataFrame:
    benchmark_symbol = benchmark_symbol.upper()
    base = attach_pre_event_price_features(
        attach_event_returns(events, close, benchmarks=[benchmark_symbol]),
        close,
        volume,
    )
    base["cluster"] = base["symbol"].map(lambda symbol: cluster_map.get(str(symbol).upper(), "unclassified"))

    calendar = pd.DatetimeIndex(close.index).sort_values()
    calendar_pos = {pd.Timestamp(date): i for i, date in enumerate(calendar)}
    rows = []
    for row in base.to_dict("records"):
        entry_date = pd.Timestamp(row["entry_date"])
        if entry_date not in calendar:
            continue
        entry_pos = calendar.get_loc(entry_date)
        lower_date = calendar[max(0, entry_pos - lookback_days)]
        completed = base[
            (base["symbol"] != row["symbol"])
            & (pd.to_datetime(base["exit_date"]) <= entry_date)
            & (pd.to_datetime(base["exit_date"]) >= lower_date)
        ].copy()
        if not completed.empty:
            completed["peer_age_trading_days"] = completed["exit_date"].map(
                lambda date: entry_pos - calendar_pos.get(pd.Timestamp(date), entry_pos)
            )
            completed["peer_recency_weight"] = np.exp(
                -np.log(2.0) * completed["peer_age_trading_days"].clip(lower=0) / max(peer_half_life_days, 1)
            )

        cluster_peers = completed[completed["cluster"] == row["cluster"]]
        sector_peers = completed
        cluster_metrics = _peer_metrics(cluster_peers, benchmark_symbol)
        sector_metrics = _peer_metrics(sector_peers, benchmark_symbol)
        target_history = base[
            (base["symbol"] == row["symbol"])
            & (pd.to_datetime(base["exit_date"]) <= entry_date)
        ]
        target_metrics = _target_history_metrics(target_history, benchmark_symbol, window=4)

        for key, value in cluster_metrics.items():
            row[f"peer_{key}"] = value
        for key, value in sector_metrics.items():
            row[f"sector_peer_{key}"] = value
        for key, value in target_metrics.items():
            row[f"target_prior_{key}_4"] = value

        rows.append(row)

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["entry_date", "symbol"]).reset_index(drop=True)
