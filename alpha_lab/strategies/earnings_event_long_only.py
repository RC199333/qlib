"""Close-to-close long-only event portfolio simulation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class EventBacktestConfig:
    max_active_positions: int = 10
    max_weight: float = 0.10
    one_way_cost_bps: float = 10.0


def _max_drawdown(ret: pd.Series) -> float:
    nav = (1 + ret.fillna(0.0)).cumprod()
    if nav.empty:
        return np.nan
    return float((nav / nav.cummax() - 1).min())


def summarize_returns(ret: pd.Series) -> Dict[str, float]:
    ret = ret.fillna(0.0)
    if ret.empty:
        return {
            "mean": np.nan,
            "std": np.nan,
            "annualized_return": np.nan,
            "information_ratio": np.nan,
            "max_drawdown": np.nan,
            "cumulative_return": np.nan,
        }
    std = ret.std()
    return {
        "mean": float(ret.mean()),
        "std": float(std),
        "annualized_return": float((1 + ret).prod() ** (252 / max(len(ret), 1)) - 1),
        "sharpe": float(ret.mean() / std * np.sqrt(252)) if std and np.isfinite(std) else np.nan,
        "information_ratio": float(ret.mean() / std * np.sqrt(252)) if std and np.isfinite(std) else np.nan,
        "max_drawdown": _max_drawdown(ret),
        "cumulative_return": float((1 + ret).prod() - 1),
    }


def summarize_yearly(daily: pd.DataFrame) -> pd.DataFrame:
    if daily.empty:
        return pd.DataFrame()
    rows = []
    for year, group in daily.groupby(daily.index.year):
        row = {
            "year": int(year),
            "strategy_net_return": float((1 + group["net_return"].fillna(0.0)).prod() - 1),
            "strategy_gross_return": float((1 + group["gross_return"].fillna(0.0)).prod() - 1),
            "max_drawdown": _max_drawdown(group["net_return"]),
            "turnover": float(group["turnover"].fillna(0.0).sum()) if "turnover" in group else np.nan,
            "avg_exposure": float(group["exposure"].fillna(0.0).mean()) if "exposure" in group else np.nan,
            "avg_active_positions": (
                float(group["active_positions"].fillna(0.0).mean()) if "active_positions" in group else np.nan
            ),
        }
        std = group["net_return"].fillna(0.0).std()
        row["sharpe"] = float(group["net_return"].fillna(0.0).mean() / std * np.sqrt(252)) if std else np.nan
        for col in group.columns:
            if col.startswith("benchmark_") and col.endswith("_return"):
                row[col.replace("_return", "_year_return")] = float((1 + group[col].fillna(0.0)).prod() - 1)
            if col.startswith("excess_vs_") and col.endswith("_return"):
                row[col.replace("_return", "_year_return")] = float((1 + group[col].fillna(0.0)).prod() - 1)
        rows.append(row)
    return pd.DataFrame(rows)


def _event_t_stat(values: pd.Series) -> float:
    values = pd.to_numeric(values, errors="coerce").dropna()
    if len(values) < 2:
        return np.nan
    std = values.std()
    if not std or not np.isfinite(std):
        return np.nan
    return float(values.mean() / (std / np.sqrt(len(values))))


def run_event_backtest(
    signals: pd.DataFrame,
    close: pd.DataFrame,
    benchmarks: Optional[Iterable[str]] = None,
    config: EventBacktestConfig = EventBacktestConfig(),
) -> Dict[str, pd.DataFrame | Dict[str, Dict[str, float]]]:
    selected = signals[signals["selected"]].copy()
    selected["entry_date"] = pd.to_datetime(selected["entry_date"]).dt.normalize()
    selected["exit_date"] = pd.to_datetime(selected["exit_date"]).dt.normalize()

    if selected.empty:
        daily = pd.DataFrame(index=pd.DatetimeIndex(close.index), columns=["gross_return", "net_return", "turnover"])
        daily = daily.fillna(0.0)
        return {
            "daily_returns": daily,
            "positions": pd.DataFrame(columns=["date", "symbol", "weight", "event_id", "score"]),
            "event_returns": selected,
            "metrics_by_year": summarize_yearly(daily),
            "summary": {"strategy_net": summarize_returns(daily["net_return"])},
        }

    calendar = pd.DatetimeIndex(close.index).sort_values()
    price_ret = close.pct_change()

    prior_weights: Dict[str, float] = {}
    daily_rows = []
    position_rows = []
    cost_rate = config.one_way_cost_bps / 10000.0

    for i in range(1, len(calendar)):
        prev_date = pd.Timestamp(calendar[i - 1])
        date = pd.Timestamp(calendar[i])
        active = selected[(selected["entry_date"] <= prev_date) & (selected["exit_date"] >= date)].copy()
        rank_col = "rank_score" if "rank_score" in active else "score"
        active = active.sort_values(rank_col, ascending=False).head(config.max_active_positions)
        if active.empty:
            weights: Dict[str, float] = {}
        else:
            weight = min(config.max_weight, 1.0 / len(active))
            weights = {str(row["symbol"]): weight for row in active.to_dict("records")}
            for row in active.to_dict("records"):
                position_rows.append(
                    {
                        "date": prev_date,
                        "symbol": row["symbol"],
                        "weight": weight,
                        "event_id": row["event_id"],
                        "score": row["score"],
                        "rank_score": row.get("rank_score", row["score"]),
                    }
                )

        all_symbols = set(prior_weights).union(weights)
        turnover = sum(abs(weights.get(symbol, 0.0) - prior_weights.get(symbol, 0.0)) for symbol in all_symbols)
        gross = 0.0
        for symbol, weight in weights.items():
            if symbol in price_ret.columns and date in price_ret.index:
                value = price_ret.at[date, symbol]
                if pd.notna(value):
                    gross += weight * float(value)
        net = gross - turnover * cost_rate
        daily_rows.append(
            {
                "date": date,
                "gross_return": gross,
                "net_return": net,
                "turnover": turnover,
                "exposure": sum(weights.values()),
                "active_positions": len(weights),
            }
        )
        prior_weights = weights

    daily = pd.DataFrame(daily_rows).set_index("date") if daily_rows else pd.DataFrame()
    benchmark_list = list(benchmarks or [])
    for benchmark in benchmark_list:
        if benchmark in close.columns and not daily.empty:
            benchmark_ret = price_ret[benchmark].reindex(daily.index).fillna(0.0)
            daily[f"benchmark_{benchmark}_return"] = benchmark_ret
            daily[f"benchmark_{benchmark}_exposure_matched_return"] = benchmark_ret * daily["exposure"].fillna(0.0)
            daily[f"excess_vs_{benchmark}_return"] = daily["net_return"] - daily[
                f"benchmark_{benchmark}_exposure_matched_return"
            ]

    event_rows = []
    for row in selected.to_dict("records"):
        symbol = row["symbol"]
        entry = pd.Timestamp(row["entry_date"])
        exit_ = pd.Timestamp(row["exit_date"])
        entry_close = close.at[entry, symbol] if symbol in close and entry in close.index else np.nan
        exit_close = close.at[exit_, symbol] if symbol in close and exit_ in close.index else np.nan
        event_return = exit_close / entry_close - 1 if pd.notna(entry_close) and entry_close else np.nan
        row["entry_close"] = entry_close
        row["exit_close"] = exit_close
        row["event_return"] = event_return
        row["event_return_after_cost"] = event_return - 2 * cost_rate if pd.notna(event_return) else np.nan
        for benchmark in benchmark_list:
            if benchmark not in close.columns or entry not in close.index or exit_ not in close.index:
                continue
            bench_entry = close.at[entry, benchmark]
            bench_exit = close.at[exit_, benchmark]
            bench_return = bench_exit / bench_entry - 1 if pd.notna(bench_entry) and bench_entry else np.nan
            row[f"benchmark_{benchmark}_event_return"] = bench_return
            row[f"excess_vs_{benchmark}_event_return"] = event_return - bench_return if pd.notna(event_return) else np.nan
        event_rows.append(row)
    event_returns = pd.DataFrame(event_rows)

    summary = {"strategy_gross": summarize_returns(daily["gross_return"]), "strategy_net": summarize_returns(daily["net_return"])}
    if not event_returns.empty:
        event_after_cost = pd.to_numeric(event_returns["event_return_after_cost"], errors="coerce")
        event_summary = {
            "selected_events": float(len(event_returns)),
            "hit_rate": float(event_after_cost.gt(0).mean()),
            "average_event_return_after_cost": float(event_after_cost.mean()),
            "median_event_return_after_cost": float(event_after_cost.median()),
            "event_return_t_stat": _event_t_stat(event_after_cost),
        }
        for benchmark in benchmark_list:
            col = f"excess_vs_{benchmark}_event_return"
            if col in event_returns:
                excess = pd.to_numeric(event_returns[col], errors="coerce")
                event_summary[f"average_{col}"] = float(excess.mean())
                event_summary[f"median_{col}"] = float(excess.median())
                event_summary[f"{col}_t_stat"] = _event_t_stat(excess)
        summary["selected_event"] = event_summary
    for benchmark in benchmarks or []:
        if benchmark in close.columns:
            bench_ret = price_ret[benchmark].reindex(daily.index).fillna(0.0)
            exposure_matched_bench = bench_ret * daily["exposure"].fillna(0.0)
            summary[f"benchmark_{benchmark}"] = summarize_returns(bench_ret)
            summary[f"benchmark_{benchmark}_exposure_matched"] = summarize_returns(exposure_matched_bench)
            summary[f"excess_vs_{benchmark}"] = summarize_returns(daily["net_return"] - exposure_matched_bench)

    return {
        "daily_returns": daily,
        "positions": pd.DataFrame(position_rows),
        "event_returns": event_returns,
        "metrics_by_year": summarize_yearly(daily),
        "summary": summary,
    }
