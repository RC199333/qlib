"""Deterministic scoring model for earnings read-through signals."""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


def _component(series: pd.Series, scale: float, lower: float = -3.0, upper: float = 3.0) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").fillna(0.0) / scale
    return values.clip(lower=lower, upper=upper)


def _centered_rate(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").fillna(0.5)
    return ((values - 0.5) * 2.0).clip(lower=-1.0, upper=1.0)


def _rolling_percentile(
    frame: pd.DataFrame,
    score_col: str,
    valid_col: str,
    min_history_events: int,
) -> pd.Series:
    percentiles = pd.Series(np.nan, index=frame.index, dtype=float)
    for idx, row in frame.iterrows():
        entry_date = pd.Timestamp(row["entry_date"])
        prior = frame[(pd.to_datetime(frame["entry_date"]) < entry_date) & frame[valid_col]]
        prior_scores = pd.to_numeric(prior[score_col], errors="coerce").dropna()
        if len(prior_scores) < min_history_events:
            continue
        value = row[score_col]
        if pd.isna(value):
            continue
        percentiles.at[idx] = float((prior_scores <= float(value)).mean())
    return percentiles


def score_readthrough_events(
    features: pd.DataFrame,
    min_peer_events: int = 3,
    score_threshold: Optional[float] = 0.25,
    selection_quantile: Optional[float] = None,
    selection_min_quantile: Optional[float] = None,
    selection_max_quantile: Optional[float] = None,
    min_history_events: int = 20,
    max_runup_5: float = 0.12,
    max_volatility_20: float = 0.08,
    min_avg_dollar_volume_20: float = 20_000_000.0,
    min_peer_excess_hit_rate: float = 0.35,
    min_target_prior_events: int = 0,
    min_target_prior_excess_median: Optional[float] = None,
    require_positive_alpha: bool = True,
) -> pd.DataFrame:
    out = features.copy()
    if out.empty:
        return out

    def col(name: str) -> pd.Series:
        return out[name] if name in out else pd.Series(np.nan, index=out.index)

    peer_surprise = col("peer_surprise_pct_mean_winsor").fillna(col("peer_surprise_pct_mean"))
    peer_excess = col("peer_event_excess_mean").fillna(col("peer_event_return_mean"))
    peer_breadth = col("peer_positive_readthrough_rate").fillna(col("peer_event_excess_hit_rate")).fillna(
        col("peer_surprise_beat_rate")
    )
    peer_count = pd.to_numeric(col("peer_event_count"), errors="coerce").fillna(0.0)

    sector_excess = col("sector_peer_event_excess_mean").fillna(peer_excess)
    sector_breadth = col("sector_peer_positive_readthrough_rate").fillna(peer_breadth)

    out["peer_surprise_component"] = _component(peer_surprise, 25.0)
    out["peer_excess_component"] = _component(peer_excess, 0.04)
    out["peer_breadth_component"] = _centered_rate(peer_breadth)
    out["peer_count_component"] = (np.log1p(peer_count) / np.log1p(8)).clip(lower=0.0, upper=1.0)
    out["sector_excess_component"] = _component(sector_excess, 0.04)
    out["sector_breadth_component"] = _centered_rate(sector_breadth)

    out["momentum_component"] = _component(col("momentum_20"), 0.10)
    out["abnormal_volume_component"] = _component(col("abnormal_volume_10"), 1.0)
    out["runup_component"] = _component(col("runup_5"), 0.08)
    out["volatility_component"] = _component(col("volatility_20"), 0.04, lower=0.0, upper=3.0)
    out["target_prior_excess_component"] = _component(col("target_prior_event_excess_median_4"), 0.03)
    out["target_prior_hit_component"] = _centered_rate(col("target_prior_event_excess_hit_rate_4"))
    out["target_quality_score"] = (
        0.65 * out["target_prior_excess_component"] + 0.35 * out["target_prior_hit_component"]
    )

    out["alpha_score"] = (
        0.38 * out["peer_surprise_component"]
        + 0.34 * out["peer_excess_component"]
        + 0.18 * out["peer_breadth_component"]
        + 0.05 * out["peer_count_component"]
        + 0.03 * out["sector_excess_component"]
        + 0.02 * out["sector_breadth_component"]
    )
    out["setup_score"] = (
        0.45 * out["momentum_component"]
        + 0.25 * out["abnormal_volume_component"]
        - 0.20 * out["runup_component"].clip(lower=0.0)
        - 0.10 * out["volatility_component"]
    )
    out["rank_score"] = out["alpha_score"] + 0.10 * out["setup_score"] + 0.15 * out["target_quality_score"]
    out["score"] = out["alpha_score"]

    setup_runup_pass = pd.to_numeric(col("runup_5"), errors="coerce").fillna(0.0) <= max_runup_5
    setup_vol_pass = pd.to_numeric(col("volatility_20"), errors="coerce").fillna(0.0) <= max_volatility_20
    setup_liquidity_pass = (
        pd.to_numeric(col("avg_dollar_volume_20"), errors="coerce").fillna(0.0) >= min_avg_dollar_volume_20
    )
    peer_breadth_pass = pd.to_numeric(col("peer_event_excess_hit_rate"), errors="coerce").fillna(0.0) >= (
        min_peer_excess_hit_rate
    )
    target_prior_count = pd.to_numeric(col("target_prior_event_count_4"), errors="coerce").fillna(0.0)
    target_quality_pass = target_prior_count >= min_target_prior_events
    if min_target_prior_excess_median is not None:
        target_quality_pass = target_quality_pass & (
            pd.to_numeric(col("target_prior_event_excess_median_4"), errors="coerce").fillna(-np.inf)
            > min_target_prior_excess_median
        )
    out["setup_filter_pass"] = setup_runup_pass & setup_vol_pass & setup_liquidity_pass
    out["peer_breadth_filter_pass"] = peer_breadth_pass
    out["target_quality_filter_pass"] = target_quality_pass
    out["eligible"] = (
        (peer_count >= min_peer_events)
        & pd.to_numeric(col("entry_close"), errors="coerce").notna()
        & pd.to_numeric(col("exit_close"), errors="coerce").notna()
    )
    out["pre_target_tradable_signal"] = out["eligible"] & out["setup_filter_pass"] & out["peer_breadth_filter_pass"]
    if require_positive_alpha:
        out["pre_target_tradable_signal"] = out["pre_target_tradable_signal"] & (
            pd.to_numeric(out["alpha_score"], errors="coerce") > 0
        )
    out["tradable_signal"] = out["pre_target_tradable_signal"] & out["target_quality_filter_pass"]

    out = out.sort_values(["entry_date", "rank_score"], ascending=[True, False]).reset_index(drop=True)
    if selection_quantile is not None or selection_min_quantile is not None or selection_max_quantile is not None:
        out["score_percentile_history"] = _rolling_percentile(
            out,
            score_col="alpha_score",
            valid_col="pre_target_tradable_signal",
            min_history_events=min_history_events,
        )
        lower = selection_min_quantile if selection_min_quantile is not None else selection_quantile
        upper = selection_max_quantile if selection_max_quantile is not None else 1.0
        lower = 0.0 if lower is None else lower
        out["selected"] = (
            out["tradable_signal"]
            & (out["score_percentile_history"] >= lower)
            & (out["score_percentile_history"] <= upper)
        )
    else:
        out["score_percentile_history"] = np.nan
        threshold = 0.0 if score_threshold is None else score_threshold
        out["selected"] = out["tradable_signal"] & (out["alpha_score"] >= threshold)

    out["signal"] = out["alpha_score"].where(out["eligible"])
    return out.sort_values(["entry_date", "score"], ascending=[True, False]).reset_index(drop=True)
