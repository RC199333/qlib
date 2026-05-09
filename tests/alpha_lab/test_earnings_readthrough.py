from __future__ import annotations

import pandas as pd

from alpha_lab.data_sources.alpha_vantage import normalize_earnings_payload
from alpha_lab.earnings.events import prepare_earnings_events
from alpha_lab.earnings.features import build_readthrough_features
from alpha_lab.models.readthrough import score_readthrough_events
from alpha_lab.strategies.earnings_event_long_only import EventBacktestConfig, run_event_backtest


def _sample_prices():
    dates = pd.bdate_range("2024-01-02", "2024-01-16")
    close = pd.DataFrame(
        {
            "PEER1": [100, 101, 102, 104, 111, 112, 113, 114, 115, 116, 117],
            "PEER2": [50, 51, 52, 53, 54, 58, 59, 60, 61, 62, 63],
            "TARGET": [200, 201, 202, 203, 204, 205, 210, 220, 225, 226, 227],
            "QQQ": [400, 401, 402, 403, 404, 405, 406, 407, 408, 409, 410],
        },
        index=dates,
    )
    volume = pd.DataFrame(1_000_000, index=dates, columns=close.columns)
    return close, volume


def test_alpha_vantage_earnings_normalization():
    payload = {
        "quarterlyEarnings": [
            {
                "reportedDate": "2024-01-05",
                "fiscalDateEnding": "2023-12-31",
                "reportedEPS": "2.0",
                "estimatedEPS": "1.5",
                "surprise": "0.5",
                "surprisePercentage": "33.3333",
            }
        ]
    }
    df = normalize_earnings_payload("peer1", payload)
    assert df.loc[0, "symbol"] == "PEER1"
    assert df.loc[0, "reported_eps"] == 2.0
    assert df.loc[0, "surprise_percentage"] == 33.3333


def test_readthrough_uses_only_completed_peer_events():
    close, volume = _sample_prices()
    raw_events = pd.DataFrame(
        [
            {"symbol": "PEER1", "reported_date": "2024-01-05", "surprise_percentage": 20.0},
            {"symbol": "PEER2", "reported_date": "2024-01-08", "surprise_percentage": 10.0},
            {"symbol": "TARGET", "reported_date": "2024-01-10", "surprise_percentage": -99.0},
        ]
    )
    events = prepare_earnings_events(raw_events, close.index)
    features = build_readthrough_features(
        events,
        close,
        volume,
        {"PEER1": "semis", "PEER2": "semis", "TARGET": "semis"},
        lookback_days=15,
    )
    target = features[features["symbol"] == "TARGET"].iloc[0]
    assert target["peer_event_count"] == 2
    assert target["peer_surprise_pct_mean"] == 15.0
    assert target["surprise_percentage"] == -99.0


def test_scoring_and_event_backtest_select_positive_readthrough():
    close, volume = _sample_prices()
    raw_events = pd.DataFrame(
        [
            {"symbol": "PEER1", "reported_date": "2024-01-05", "surprise_percentage": 20.0},
            {"symbol": "PEER2", "reported_date": "2024-01-08", "surprise_percentage": 10.0},
            {"symbol": "TARGET", "reported_date": "2024-01-10", "surprise_percentage": 0.0},
        ]
    )
    events = prepare_earnings_events(raw_events, close.index)
    features = build_readthrough_features(
        events,
        close,
        volume,
        {"PEER1": "semis", "PEER2": "semis", "TARGET": "semis"},
        lookback_days=15,
    )
    signals = score_readthrough_events(features, min_peer_events=2, score_threshold=0.1)
    assert signals[signals["symbol"] == "TARGET"].iloc[0]["selected"]

    result = run_event_backtest(
        signals,
        close,
        benchmarks=["QQQ"],
        config=EventBacktestConfig(max_active_positions=2, max_weight=0.5, one_way_cost_bps=0),
    )
    event_returns = result["event_returns"]
    target_return = event_returns[event_returns["symbol"] == "TARGET"].iloc[0]["event_return"]
    assert round(target_return, 6) == round(220 / 205 - 1, 6)
    assert result["summary"]["strategy_net"]["cumulative_return"] > 0


def test_rolling_percentile_selection_uses_prior_events_only():
    dates = pd.bdate_range("2024-01-02", periods=6)
    features = pd.DataFrame(
        {
            "symbol": [f"T{i}" for i in range(6)],
            "entry_date": dates,
            "exit_date": dates + pd.offsets.BDay(1),
            "event_id": [f"T{i}_202401" for i in range(6)],
            "entry_close": 100.0,
            "exit_close": 101.0,
            "event_return": 0.01,
            "peer_event_count": 3,
            "peer_surprise_pct_mean_winsor": [5, 10, 15, 20, 25, 30],
            "peer_event_excess_mean": [0.01, 0.015, 0.02, 0.025, 0.03, 0.035],
            "peer_positive_readthrough_rate": 0.60,
            "peer_event_excess_hit_rate": 0.60,
            "sector_peer_event_excess_mean": [0.01, 0.015, 0.02, 0.025, 0.03, 0.035],
            "sector_peer_positive_readthrough_rate": 0.60,
            "momentum_20": 0.0,
            "abnormal_volume_10": 0.0,
            "runup_5": 0.0,
            "volatility_20": 0.01,
            "avg_dollar_volume_20": 100_000_000.0,
        }
    )
    signals = score_readthrough_events(
        features,
        min_peer_events=3,
        selection_min_quantile=0.5,
        selection_max_quantile=1.0,
        min_history_events=2,
        score_threshold=None,
    )

    ordered = signals.sort_values("entry_date").reset_index(drop=True)
    assert ordered.loc[0:1, "score_percentile_history"].isna().all()
    assert not ordered.loc[0:1, "selected"].any()
    assert ordered.loc[2, "score_percentile_history"] == 1.0
    assert ordered.loc[2, "selected"]
