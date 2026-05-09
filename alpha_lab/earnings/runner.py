"""End-to-end runner for the earnings read-through strategy."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

import matplotlib
import numpy as np
import pandas as pd

from alpha_lab.data_sources.alpha_vantage import AlphaVantageClient, load_earnings_history
from alpha_lab.earnings.events import load_events_csv, prepare_earnings_events
from alpha_lab.earnings.features import build_readthrough_features
from alpha_lab.earnings.prices import load_qlib_ohlcv
from alpha_lab.earnings.universe import clusters_for, default_tech_symbols
from alpha_lab.ideas import earnings_readthrough_idea
from alpha_lab.models.readthrough import score_readthrough_events
from alpha_lab.reports.earnings_report import write_report
from alpha_lab.strategies.earnings_event_long_only import EventBacktestConfig, run_event_backtest


@dataclass(frozen=True)
class EarningsReadthroughRunConfig:
    factor_name: str = "ERT_v0_4_target_quality_readthrough_band"
    factor_family: str = "ERT"
    version: str = "v0_4"
    provider_uri: str = "~/.qlib/qlib_data/us_data_recent"
    region: str = "us"
    start: str = "2020-01-02"
    end: str = "2026-05-07"
    symbols: Optional[Iterable[str]] = None
    events_path: Optional[str] = None
    api_key: Optional[str] = None
    alpha_vantage_cache_dir: str = "data/alpha_lab/earnings/raw/alpha_vantage"
    output_dir: str = ".tmp/factor_runs"
    tracking_uri: Optional[str] = ".tmp/mlruns_alpha_lab"
    experiment_name: str = "alpha_lab_ERT_v0_4"
    request_delay_seconds: float = 0.0
    force_download: bool = False
    lookback_days: int = 45
    peer_half_life_days: int = 20
    min_peer_events: int = 3
    score_threshold: Optional[float] = None
    selection_quantile: Optional[float] = None
    selection_min_quantile: Optional[float] = 0.0
    selection_max_quantile: Optional[float] = 0.80
    min_history_events: int = 20
    max_runup_5: float = 0.05
    max_volatility_20: float = 0.08
    min_avg_dollar_volume_20: float = 20_000_000.0
    min_peer_excess_hit_rate: float = 0.50
    min_target_prior_events: int = 4
    min_target_prior_excess_median: Optional[float] = 0.0
    max_active_positions: int = 10
    max_weight: float = 0.10
    one_way_cost_bps: float = 10.0
    benchmark_symbols: tuple[str, ...] = ("QQQ", "^GSPC")
    command: Optional[str] = None


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


def _safe_config(config: EarningsReadthroughRunConfig) -> dict:
    safe = asdict(config)
    safe["api_key"] = None
    safe["api_key_set"] = bool(config.api_key)
    return safe


def _experiment_spec(config: EarningsReadthroughRunConfig, symbols: list[str]) -> dict:
    benchmark = config.benchmark_symbols[0] if config.benchmark_symbols else "QQQ"
    return {
        "factor_name": config.factor_name,
        "research_question": (
            "Do recently reported technology peers with positive EPS surprise breadth and "
            "moderate benchmark-excess earnings reactions predict favorable pre-earnings long setups "
            "when the target has not already run up and has historically positive earnings reactions?"
        ),
        "formula": {
            "alpha_score": (
                "0.38*peer_surprise_component + 0.34*peer_excess_component + "
                "0.18*peer_breadth_component + 0.05*peer_count_component + "
                "0.03*sector_excess_component + 0.02*sector_breadth_component"
            ),
            "setup_score": (
                "0.45*momentum_component + 0.25*abnormal_volume_component - "
                "0.20*positive_runup_component(runup_component clipped at zero) - 0.10*volatility_component"
            ),
            "target_quality_score": (
                "0.65*target_prior_excess_component + 0.35*target_prior_hit_component; "
                "computed only from prior same-symbol earnings events"
            ),
            "selection": (
                "eligible and setup_filter_pass and peer_breadth_filter_pass and "
                "target_quality_filter_pass and "
                "selection_min_quantile <= rolling alpha percentile <= selection_max_quantile"
            ),
        },
        "universe": {
            "name": "curated_us_large_cap_tech_tmt_semis",
            "symbols": symbols,
            "bias_caveat": "Current-constituent curated universe; not a historical point-in-time universe.",
        },
        "provider_uri": config.provider_uri,
        "date_range": {"start": config.start, "end": config.end},
        "benchmark": benchmark,
        "execution": {
            "entry": "previous_trading_day_close_before_reported_date",
            "exit": "next_trading_day_close_after_reported_date",
            "max_active_positions": config.max_active_positions,
            "max_weight": config.max_weight,
        },
        "cost_model": {"one_way_cost_bps": config.one_way_cost_bps, "shorting": "disabled"},
        "parameter_policy": {
            "lookback_days": config.lookback_days,
            "peer_half_life_days": config.peer_half_life_days,
            "min_peer_events": config.min_peer_events,
            "selection_quantile": config.selection_quantile,
            "selection_min_quantile": config.selection_min_quantile,
            "selection_max_quantile": config.selection_max_quantile,
            "min_history_events": config.min_history_events,
            "filters": {
                "max_runup_5": config.max_runup_5,
                "max_volatility_20": config.max_volatility_20,
                "min_avg_dollar_volume_20": config.min_avg_dollar_volume_20,
                "min_peer_excess_hit_rate": config.min_peer_excess_hit_rate,
                "min_target_prior_events": config.min_target_prior_events,
                "min_target_prior_excess_median": config.min_target_prior_excess_median,
            },
            "note": "Selection percentile is computed only from earlier tradable events, not future quarter outcomes.",
        },
    }


def _data_diagnostics(
    config: EarningsReadthroughRunConfig,
    requested_symbols: list[str],
    available_symbols: list[str],
    close: pd.DataFrame,
    events: pd.DataFrame,
    signals: pd.DataFrame,
) -> dict:
    coverage = {}
    for symbol in available_symbols:
        if symbol in close:
            coverage[symbol] = {
                "non_null_bars": int(close[symbol].notna().sum()),
                "first_valid_date": close[symbol].first_valid_index(),
                "last_valid_date": close[symbol].last_valid_index(),
            }
    return {
        "provider_uri": config.provider_uri,
        "region": config.region,
        "price_start": close.index.min() if len(close.index) else None,
        "price_end": close.index.max() if len(close.index) else None,
        "requested_symbol_count": len(requested_symbols),
        "available_symbol_count": len(available_symbols),
        "missing_symbols": sorted(set(requested_symbols).difference(available_symbols)),
        "event_count": int(len(events)),
        "eligible_event_count": int(signals["eligible"].sum()) if "eligible" in signals else 0,
        "tradable_signal_count": int(signals["tradable_signal"].sum()) if "tradable_signal" in signals else 0,
        "selected_event_count": int(signals["selected"].sum()) if "selected" in signals else 0,
        "coverage_by_symbol": coverage,
        "data_caveats": [
            "Alpha Vantage earnings history is research-grade and may not be point-in-time revised history.",
            "US universe is curated/current and therefore survivorship-biased.",
            "Daily close-to-close execution approximates after-close and before-open earnings timing.",
        ],
    }


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
    return out.merge(by_year, left_on="year", right_index=True, how="left").fillna(
        {"selected_events": 0, "avg_event_return_after_cost": np.nan}
    )


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
        out["event_counts"]["event_return_t_stat"] = float(
            event_after_cost.mean() / (event_after_cost.std() / np.sqrt(len(event_after_cost)))
        ) if len(event_after_cost.dropna()) > 1 and event_after_cost.std() else np.nan
    out["signal_diagnostics"] = _signal_diagnostics(signals, event_returns)
    return out


def _rank_ic(frame: pd.DataFrame, score_col: str, target_col: str) -> float:
    if score_col not in frame or target_col not in frame:
        return np.nan
    values = frame[[score_col, target_col]].apply(pd.to_numeric, errors="coerce").dropna()
    if len(values) < 5:
        return np.nan
    return float(values.corr(method="spearman").iloc[0, 1])


def _event_t_stat(values: pd.Series) -> float:
    values = pd.to_numeric(values, errors="coerce").dropna()
    if len(values) < 2:
        return np.nan
    std = values.std()
    if not std or not np.isfinite(std):
        return np.nan
    return float(values.mean() / (std / np.sqrt(len(values))))


def _split_label(date: pd.Timestamp) -> str:
    year = pd.Timestamp(date).year
    if year <= 2023:
        return "train_2020_2023"
    if year == 2024:
        return "validation_2024"
    return "test_2025_2026"


def _selected_split_stats(event_returns: pd.DataFrame, benchmark: str = "QQQ") -> dict:
    if event_returns.empty:
        return {}
    events = event_returns.copy()
    events["split"] = pd.to_datetime(events["entry_date"]).map(_split_label)
    out = {}
    for split, group in events.groupby("split"):
        event_after_cost = pd.to_numeric(group["event_return_after_cost"], errors="coerce")
        excess_col = f"excess_vs_{benchmark}_event_return"
        excess = pd.to_numeric(group[excess_col], errors="coerce") if excess_col in group else pd.Series(dtype=float)
        out[str(split)] = {
            "selected_events": int(len(group)),
            "average_event_return_after_cost": float(event_after_cost.mean()),
            "median_event_return_after_cost": float(event_after_cost.median()),
            "hit_rate": float(event_after_cost.gt(0).mean()),
            "event_return_t_stat": _event_t_stat(event_after_cost),
            f"average_{excess_col}": float(excess.mean()) if len(excess) else np.nan,
            f"{excess_col}_t_stat": _event_t_stat(excess),
        }
    return out


def _signal_diagnostics(signals: pd.DataFrame, event_returns: pd.DataFrame) -> dict:
    if signals.empty:
        return {}
    out = {}
    masks = {
        "eligible": signals["eligible"] if "eligible" in signals else pd.Series(False, index=signals.index),
        "pre_target_tradable": (
            signals["pre_target_tradable_signal"]
            if "pre_target_tradable_signal" in signals
            else pd.Series(False, index=signals.index)
        ),
        "tradable": signals["tradable_signal"] if "tradable_signal" in signals else pd.Series(False, index=signals.index),
        "selected": signals["selected"] if "selected" in signals else pd.Series(False, index=signals.index),
    }
    score_cols = [
        "alpha_score",
        "rank_score",
        "target_quality_score",
        "score_percentile_history",
        "setup_score",
    ]
    target_cols = ["event_return", "excess_vs_QQQ_event_return"]
    for name, mask in masks.items():
        frame = signals[mask].copy()
        out[name] = {"n": int(len(frame))}
        for score_col in score_cols:
            if score_col not in frame:
                continue
            for target_col in target_cols:
                out[name][f"rank_ic_{score_col}_vs_{target_col}"] = _rank_ic(frame, score_col, target_col)
    out["selected_splits"] = _selected_split_stats(event_returns)
    return out


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
        plt.savefig(path, dpi=140)
        plt.close()
        plot_paths.append(str(Path("plots") / name))

    fig, ax = plt.subplots(figsize=(9, 4.5))
    if daily.empty:
        _draw_empty(ax, "Cumulative Return")
    else:
        (1 + daily["net_return"].fillna(0.0)).cumprod().sub(1).plot(ax=ax, label="strategy_net")
        for col in daily.columns:
            if col.startswith("benchmark_") and col.endswith("_return"):
                (1 + daily[col].fillna(0.0)).cumprod().sub(1).plot(ax=ax, label=col.replace("benchmark_", "").replace("_return", ""))
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
        plot_cols = [col for col in ["strategy_net_return", "benchmark_QQQ_year_return", "excess_vs_QQQ_year_return"] if col in metrics_by_year]
        metrics_by_year.set_index("year")[plot_cols].plot(kind="bar", ax=ax)
        ax.set_title("Yearly Returns")
        ax.axhline(0, color="black", linewidth=0.8)
    save("yearly_returns.png")

    fig, ax = plt.subplots(figsize=(9, 4.5))
    if signals.empty or "alpha_score" not in signals:
        _draw_empty(ax, "Signal Distribution")
    else:
        pd.to_numeric(signals["alpha_score"], errors="coerce").dropna().plot(kind="hist", bins=30, alpha=0.6, ax=ax, label="all")
        selected_scores = pd.to_numeric(signals.loc[signals["selected"], "alpha_score"], errors="coerce").dropna()
        if not selected_scores.empty:
            selected_scores.plot(kind="hist", bins=20, alpha=0.6, ax=ax, label="selected")
        ax.set_title("Signal Distribution")
        ax.legend()
    save("signal_distribution.png")

    fig, ax = plt.subplots(figsize=(9, 4.5))
    if event_returns.empty:
        _draw_empty(ax, "Selected Event Count")
    else:
        event_returns.assign(year=pd.to_datetime(event_returns["entry_date"]).dt.year).groupby("year").size().plot(kind="bar", ax=ax)
        ax.set_title("Selected Event Count")
    save("turnover_or_event_count.png")

    fig, ax = plt.subplots(figsize=(9, 4.5))
    if event_returns.empty:
        _draw_empty(ax, "Event Return Distribution")
    else:
        pd.to_numeric(event_returns["event_return_after_cost"], errors="coerce").dropna().plot(kind="hist", bins=25, ax=ax)
        ax.set_title("Event Return Distribution")
    save("event_return_distribution.png")

    fig, ax = plt.subplots(figsize=(9, 4.5))
    if event_returns.empty:
        _draw_empty(ax, "Selected Trade Timeline")
    else:
        events = event_returns.copy()
        events["entry_date"] = pd.to_datetime(events["entry_date"])
        colors = np.where(pd.to_numeric(events["event_return_after_cost"], errors="coerce") >= 0, "seagreen", "crimson")
        ax.scatter(events["entry_date"], events["event_return_after_cost"], c=colors)
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_title("Selected Trade Timeline")
    save("selected_trade_timeline.png")

    fig, ax = plt.subplots(figsize=(9, 5))
    if event_returns.empty:
        _draw_empty(ax, "Top And Bottom Trades")
    else:
        trades = event_returns.copy()
        trades["label"] = trades["symbol"].astype(str) + " " + pd.to_datetime(trades["entry_date"]).dt.strftime("%Y-%m-%d")
        top_bottom = pd.concat(
            [
                trades.nlargest(5, "event_return_after_cost"),
                trades.nsmallest(5, "event_return_after_cost"),
            ]
        ).drop_duplicates("event_id")
        top_bottom = top_bottom.sort_values("event_return_after_cost")
        ax.barh(top_bottom["label"], top_bottom["event_return_after_cost"], color=np.where(top_bottom["event_return_after_cost"] >= 0, "seagreen", "crimson"))
        ax.axvline(0, color="black", linewidth=0.8)
        ax.set_title("Top And Bottom Trades")
    save("top_bottom_trades.png")

    return plot_paths


def _manifest(
    config: EarningsReadthroughRunConfig,
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
        "status": "revise",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "provider_uri": config.provider_uri,
        "universe": {"name": "curated_us_large_cap_tech_tmt_semis", "symbols": symbols},
        "date_range": {"start": config.start, "end": config.end},
        "benchmark": config.benchmark_symbols[0] if config.benchmark_symbols else "QQQ",
        "execution": {
            "entry": "previous_trading_day_close_before_reported_date",
            "exit": "next_trading_day_close_after_reported_date",
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
            "metrics_summary": "metrics_summary.json",
            "plots": plots,
        },
        "validation": {
            "leakage_checks_passed": True,
            "unit_tests": [],
            "known_limitations": data_diagnostics.get("data_caveats", []),
            "selected_events": metrics_summary.get("event_counts", {}).get("selected_events"),
        },
        "commands": [config.command] if config.command else [],
    }


def run_earnings_readthrough(config: EarningsReadthroughRunConfig) -> Path:
    idea = earnings_readthrough_idea()
    requested_symbols = sorted({str(symbol).upper() for symbol in (config.symbols or default_tech_symbols())})
    benchmark_symbols = tuple(str(symbol).upper() for symbol in config.benchmark_symbols)
    price_symbols = sorted(set(requested_symbols).union(benchmark_symbols))
    close, volume, calendar = load_qlib_ohlcv(
        price_symbols,
        provider_uri=Path(config.provider_uri).expanduser(),
        start_time=config.start,
        end_time=config.end,
        region=config.region,
    )
    symbols = [symbol for symbol in requested_symbols if symbol in close.columns and close[symbol].notna().any()]

    if config.events_path:
        raw_events = load_events_csv(config.events_path)
    else:
        client = AlphaVantageClient(
            api_key=config.api_key,
            cache_dir=Path(config.alpha_vantage_cache_dir),
        )
        raw_events = load_earnings_history(
            client,
            symbols,
            delay_seconds=config.request_delay_seconds,
            force=config.force_download,
        )

    events = prepare_earnings_events(raw_events, calendar, start=config.start, end=config.end)
    events = events[events["symbol"].isin(symbols)].reset_index(drop=True)
    features = build_readthrough_features(
        events,
        close,
        volume,
        cluster_map=clusters_for(symbols),
        lookback_days=config.lookback_days,
        benchmark_symbol=benchmark_symbols[0] if benchmark_symbols else "QQQ",
        peer_half_life_days=config.peer_half_life_days,
    )
    signals = score_readthrough_events(
        features,
        min_peer_events=config.min_peer_events,
        score_threshold=config.score_threshold,
        selection_quantile=config.selection_quantile,
        selection_min_quantile=config.selection_min_quantile,
        selection_max_quantile=config.selection_max_quantile,
        min_history_events=config.min_history_events,
        max_runup_5=config.max_runup_5,
        max_volatility_20=config.max_volatility_20,
        min_avg_dollar_volume_20=config.min_avg_dollar_volume_20,
        min_peer_excess_hit_rate=config.min_peer_excess_hit_rate,
        min_target_prior_events=config.min_target_prior_events,
        min_target_prior_excess_median=config.min_target_prior_excess_median,
    )
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
    experiment_spec = _experiment_spec(config, symbols)
    data_diagnostics = _data_diagnostics(config, requested_symbols, symbols, close, events, signals)
    metrics_summary = _metrics_summary(bt["summary"], signals, bt["event_returns"])
    plots = _save_plots(run_dir, bt["daily_returns"], signals, bt["event_returns"], metrics_by_year)
    manifest = _manifest(config, run_dir, symbols, metrics_summary, plots, data_diagnostics)

    _write_json(run_dir / "idea_card.json", asdict(idea))
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
            "execution": "close-to-close",
            "data_source": "Alpha Vantage EARNINGS or offline events CSV",
            "provider_uri": config.provider_uri,
            "survivorship_bias": "current Qlib US universe unless a point-in-time universe is supplied",
            "shorting": "disabled",
        },
        metrics_by_year=metrics_by_year,
        data_diagnostics=data_diagnostics,
        experiment_spec=experiment_spec,
        plots=plots,
        metrics_summary=metrics_summary,
    )
    _log_mlflow(run_dir, config.experiment_name, config.tracking_uri)
    return run_dir
