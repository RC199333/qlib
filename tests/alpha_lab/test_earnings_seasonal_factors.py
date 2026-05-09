from __future__ import annotations

import pandas as pd

from alpha_lab.earnings.seasonal_factors import SeasonalFactorRunConfig, build_pead_signals
from alpha_lab.earnings.seasonal_factors import build_pead_v2_actual_quality_signals
from alpha_lab.earnings.seasonal_factors import build_ebs_v1_signals


def test_pead_entry_starts_after_announcement_window():
    dates = pd.bdate_range("2024-01-02", periods=80)
    features = pd.DataFrame(
        {
            "symbol": ["AMD"],
            "reported_date": [pd.Timestamp("2024-01-10")],
            "fiscal_date_ending": [pd.Timestamp("2023-12-31")],
            "entry_date": [pd.Timestamp("2024-01-09")],
            "exit_date": [pd.Timestamp("2024-01-11")],
            "event_id": ["AMD_20240110"],
            "entry_close": [100.0],
            "exit_close": [110.0],
            "event_return": [0.10],
            "excess_vs_QQQ_event_return": [0.08],
            "surprise_percentage": [20.0],
            "avg_dollar_volume_20": [100_000_000.0],
            "volatility_20": [0.02],
            "runup_5": [0.01],
            "target_prior_event_excess_median_4": [0.02],
            "target_prior_surprise_beat_rate_4": [0.75],
        }
    )
    config = SeasonalFactorRunConfig(
        factor_name="PEAD_v1_quality_drift_40d",
        factor_family="PEAD",
        version="v1",
        hold_days=20,
        min_history_events=0,
    )
    signals = build_pead_signals(features, pd.DataFrame(index=dates), pd.DataFrame(index=dates), dates, config)
    assert signals.loc[0, "entry_date"] == pd.Timestamp("2024-01-11")
    assert signals.loc[0, "exit_date"] > signals.loc[0, "entry_date"]
    assert signals.loc[0, "selected"]


def test_pead_v2_requires_sec_quality_gate():
    dates = pd.bdate_range("2024-01-02", periods=120)
    features = pd.DataFrame(
        {
            "symbol": ["AMD", "QCOM", "MU", "TXN"],
            "reported_date": dates[[5, 10, 20, 30]],
            "fiscal_date_ending": [pd.Timestamp("2023-12-31")] * 4,
            "entry_date": dates[[4, 9, 19, 29]],
            "exit_date": dates[[6, 11, 21, 31]],
            "event_id": ["AMD_1", "QCOM_1", "MU_1", "TXN_1"],
            "entry_close": [100.0] * 4,
            "exit_close": [110.0] * 4,
            "event_return": [0.10] * 4,
            "excess_vs_QQQ_event_return": [0.08] * 4,
            "surprise_percentage": [20.0] * 4,
            "avg_dollar_volume_20": [100_000_000.0] * 4,
            "volatility_20": [0.02] * 4,
            "runup_5": [0.01] * 4,
            "target_prior_event_excess_median_4": [0.02] * 4,
            "target_prior_surprise_beat_rate_4": [0.75] * 4,
            "sec_revenue_yoy": [0.00, -0.30, 0.20, -0.25],
            "sec_operating_margin_delta_yoy": [0.00, -0.10, 0.05, -0.12],
            "sec_gross_margin_delta_yoy": [0.00, -0.10, 0.03, -0.12],
            "sec_accruals_to_assets": [0.02, 0.20, -0.02, 0.25],
        }
    )
    config = SeasonalFactorRunConfig(
        factor_name="PEAD_v2_actual_quality_60d",
        factor_family="PEAD",
        version="v2",
        hold_days=20,
        min_history_events=1,
        fundamental_quality_min_rank=0.35,
        fundamental_quality_min_components=2,
    )
    signals = build_pead_v2_actual_quality_signals(
        features, pd.DataFrame(index=dates), pd.DataFrame(index=dates), dates, config
    )
    selected = dict(zip(signals["symbol"], signals["selected"]))
    assert selected["AMD"]
    assert not selected["QCOM"]
    assert selected["MU"]
    assert not selected["TXN"]


def test_basket_signal_does_not_hold_indicator_only_leader():
    dates = pd.bdate_range("2024-01-02", periods=90)
    steps = list(range(len(dates)))
    close = pd.DataFrame(
        {
            "NVDA": [100 + step * 0.1 for step in steps],
            "AMD": [50 + step * 0.05 for step in steps],
            "QCOM": [60 + step * 0.05 for step in steps],
            "MU": [70 + step * 0.05 for step in steps],
            "QQQ": [400 + step * 0.1 for step in steps],
        },
        index=dates,
    )
    features = pd.DataFrame(
        {
            "symbol": ["NVDA", "AMD", "QCOM"],
            "reported_date": dates[[5, 8, 11]],
            "fiscal_date_ending": [pd.Timestamp("2023-12-31")] * 3,
            "entry_date": dates[[4, 7, 10]],
            "exit_date": dates[[6, 9, 12]],
            "event_id": ["NVDA_1", "AMD_1", "QCOM_1"],
            "entry_close": [104.0, 57.0, 70.0],
            "exit_close": [106.0, 59.0, 72.0],
            "event_return": [0.04, 0.05, 0.04],
            "excess_vs_QQQ_event_return": [0.03, 0.04, 0.03],
            "surprise_percentage": [30.0, 20.0, 10.0],
            "avg_dollar_volume_20": [100_000_000.0] * 3,
            "volatility_20": [0.02] * 3,
            "runup_5": [0.01] * 3,
        }
    )
    config = SeasonalFactorRunConfig(
        factor_name="EBS_v1_leader_confirmed_basket_drift",
        factor_family="EBS",
        version="v1",
        hold_days=10,
    )
    signals = build_ebs_v1_signals(features, close, pd.DataFrame(index=dates), dates, config)
    assert not signals.empty
    assert "NVDA" not in set(signals["symbol"])
